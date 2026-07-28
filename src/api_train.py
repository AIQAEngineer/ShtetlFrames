"""GET/POST /api/train/* — Pathé Orthodox-Jew training labels."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import ParseResult, parse_qs

from api_http import json_response
from db import (
    clear_train_clips,
    get_job,
    init_db,
    insert_queue_items,
    list_train_clips,
    set_job,
    update_train_label,
)
from pipeline_train import (
    DEFAULT_TRAIN_QUERY,
    backfill_train_thumbs,
    clear_youtube_train_ref,
    list_youtube_train_candidates,
    load_youtube_train_ref,
    start_train_seed,
    start_youtube_train_ref,
    youtube_video_id,
)


def _query_from_qs(qs: dict, body: dict | None = None) -> str:
    if body and isinstance(body, dict) and body.get("query") is not None:
        return str(body.get("query") or "").strip()
    return ((qs.get("query") or [DEFAULT_TRAIN_QUERY])[0] or "").strip()


def handle_get_summary(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    init_db()
    qs = parse_qs(parsed.query)
    query = _query_from_qs(qs)
    data = (
        list_train_clips(query=query, limit=1, offset=0)
        if query
        else {
            "stats": {"n_total": 0, "n_pending": 0, "n_yes": 0, "n_no": 0},
        }
    )
    search_url = (
        (
            "https://www.britishpathe.com/search/"
            f"?searchQuery={query}&page=null&refined[]=&selection="
        )
        if query
        else ""
    )
    yt = load_youtube_train_ref()
    yt_stats = None
    if yt:
        yt_stats = list_youtube_train_candidates(limit=1).get("stats")
    clip_meta = None
    try:
        from clip_ft import clip_ft_dir, probe_path

        metrics_path = clip_ft_dir() / "metrics.json"
        if metrics_path.is_file():
            import json

            clip_meta = json.loads(metrics_path.read_text(encoding="utf-8"))
        elif probe_path().is_file():
            clip_meta = {"ok": True, "probe_path": str(probe_path())}
    except Exception:
        clip_meta = None
    json_response(
        handler,
        200,
        {
            "ok": True,
            "query": query,
            "search_url": search_url,
            "stats": data.get("stats") or {},
            "seed": get_job("train_seed"),
            "clip_ft": get_job("clip_ft"),
            "clip_metrics": clip_meta,
            "youtube_ref": yt,
            "youtube_stats": yt_stats,
        },
    )


def handle_get_clips(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    init_db()
    qs = parse_qs(parsed.query)
    query = _query_from_qs(qs)
    if not query:
        json_response(
            handler,
            200,
            {
                "ok": True,
                "query": "",
                "clips": [],
                "total": 0,
                "offset": 0,
                "limit": 0,
                "stats": {"n_total": 0, "n_pending": 0, "n_yes": 0, "n_no": 0},
            },
        )
        return
    status = (qs.get("status") or [""])[0]
    q = (qs.get("q") or [""])[0]
    try:
        limit = int((qs.get("limit") or ["500"])[0])
    except (TypeError, ValueError):
        limit = 500
    try:
        offset = int((qs.get("offset") or ["0"])[0])
    except (TypeError, ValueError):
        offset = 0
    data = list_train_clips(
        query=query, status=status, q=q, limit=limit, offset=offset
    )
    json_response(handler, 200, {"ok": True, "query": query, **data})


def handle_post_seed(handler: BaseHTTPRequestHandler, body: dict) -> None:
    body = body if isinstance(body, dict) else {}
    query = str(body.get("query") or DEFAULT_TRAIN_QUERY).strip()
    if not query:
        json_response(handler, 400, {"ok": False, "error": "missing Pathé search query"})
        return
    max_items = body.get("max_items", 500)
    resume = body.get("resume", True)
    if isinstance(resume, str):
        resume = resume.strip().lower() not in ("0", "false", "no", "")
    result = start_train_seed(query=query, max_items=max_items, resume=bool(resume))
    code = 200 if result.get("ok") else 409
    json_response(handler, code, result)


def handle_post_clear(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """Wipe training clips (all, or one search query)."""
    init_db()
    body = body if isinstance(body, dict) else {}
    query = body.get("query")
    q = str(query).strip() if query not in (None, "") else None
    n = clear_train_clips(query=q)
    clear_youtube_train_ref()
    set_job(
        "train_seed",
        status="idle",
        phase="idle",
        message="",
        progress=0,
        discovered=0,
        total=0,
        completed=0,
        hits=0,
        error="",
    )
    json_response(
        handler,
        200,
        {"ok": True, "deleted": n, "query": q or ""},
    )


def handle_post_youtube(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """Scan a YouTube video as an Orthodox-look positive training reference."""
    body = body if isinstance(body, dict) else {}
    url = str(body.get("url") or body.get("query") or "").strip()
    title = str(body.get("title") or "").strip()
    if not youtube_video_id(url):
        json_response(
            handler,
            400,
            {"ok": False, "error": "paste a YouTube watch URL"},
        )
        return
    result = start_youtube_train_ref(url, title=title)
    code = 200 if result.get("ok") else 400
    json_response(handler, code, result)


def handle_get_youtube(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    init_db()
    qs = parse_qs(parsed.query)
    try:
        limit = int((qs.get("limit") or ["500"])[0])
    except (TypeError, ValueError):
        limit = 500
    status = (qs.get("status") or [""])[0].strip().lower()
    data = list_youtube_train_candidates(limit=limit)
    clips = list(data.get("clips") or [])
    if status in ("pending", "unlabeled"):
        clips = [c for c in clips if not (c.get("decision") or "").strip()]
    elif status in ("yes", "accept", "orthodox"):
        clips = [c for c in clips if (c.get("decision") or "") == "accept"]
    elif status in ("no", "reject", "not"):
        clips = [c for c in clips if (c.get("decision") or "") == "reject"]
    # Normalize for train.js (thumb_url + asset-style fields).
    out = []
    for c in clips:
        d = dict(c)
        d["thumb_url"] = (
            d.get("contact_url")
            or d.get("image_url")
            or d.get("still_url")
            or ""
        )
        if not d["thumb_url"] and d.get("id") is not None:
            d["thumb_url"] = f"/media/sheet/cand_{int(d['id'])}.jpg"
        d["asset_id"] = d.get("video_id") or d.get("id")
        d["title"] = d.get("video_id") or d.get("title") or "YouTube hit"
        d["url"] = d.get("source_url") or ""
        if d.get("decision") == "accept":
            d["decision"] = "yes"
        elif d.get("decision") == "reject":
            d["decision"] = "no"
        out.append(d)
    n_yes = sum(1 for c in out if (c.get("decision") or "") == "accept")
    n_no = sum(1 for c in out if (c.get("decision") or "") == "reject")
    n_pending = sum(1 for c in out if not (c.get("decision") or "").strip())
    json_response(
        handler,
        200,
        {
            "ok": True,
            "mode": "youtube",
            "ref": data.get("ref"),
            "clips": out,
            "total": len(out),
            "stats": {
                "n_total": len(out),
                "n_pending": n_pending,
                "n_yes": n_yes,
                "n_no": n_no,
            },
        },
    )


def handle_post_thumbs(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """Backfill missing Pathé thumbnail URLs for the training set."""
    body = body if isinstance(body, dict) else {}
    query = str(body.get("query") or DEFAULT_TRAIN_QUERY).strip()
    if not query:
        json_response(handler, 400, {"ok": False, "error": "missing Pathé search query"})
        return
    try:
        max_pages = int(body.get("max_pages") or 8)
    except (TypeError, ValueError):
        max_pages = 8
    result = backfill_train_thumbs(query=query, max_pages=max_pages)
    code = 200 if result.get("ok") else 409
    json_response(handler, code, result)


def handle_post_label(handler: BaseHTTPRequestHandler, body: dict) -> None:
    init_db()
    body = body if isinstance(body, dict) else {}
    decision = str(body.get("decision") or "")
    notes = str(body.get("notes") or "")
    clip_id = body.get("id")
    url = str(body.get("url") or "")
    mode = str(body.get("mode") or "").strip().lower()
    try:
        cid = int(clip_id) if clip_id not in (None, "") else None
    except (TypeError, ValueError):
        json_response(handler, 400, {"ok": False, "error": "bad id"})
        return

    # YouTube reference hits live in ``candidates`` (Review), not train_clips.
    if mode == "youtube" or body.get("candidate"):
        from db import update_review
        from label_feedback import build_fewshot_content_parts

        if cid is None:
            json_response(handler, 400, {"ok": False, "error": "missing candidate id"})
            return
        dec = decision.strip().lower()
        if dec in ("yes", "orthodox", "accept", "keep"):
            dec = "accept"
        elif dec in ("no", "not", "reject", "pass"):
            dec = "reject"
        elif dec in ("clear", "undo", "skip", ""):
            dec = ""
        else:
            json_response(handler, 400, {"ok": False, "error": "bad decision"})
            return
        note = notes or ""
        if dec == "accept" and "train:orthodox_ref" not in note.lower():
            note = f"train:orthodox_ref\n{note}".strip()
        update_review(cid, dec, note)
        try:
            build_fewshot_content_parts(force=True)
        except Exception:
            pass
        data = list_youtube_train_candidates(limit=2000)
        row = next(
            (c for c in (data.get("clips") or []) if int(c.get("id") or 0) == cid),
            None,
        )
        if row:
            row = dict(row)
            row["thumb_url"] = row.get("image_url") or f"/media/sheet/cand_{cid}.jpg"
            row["asset_id"] = row.get("video_id") or cid
            row["url"] = row.get("source_url") or ""
            # Map accept/reject → yes/no for train UI badges.
            if row.get("decision") == "accept":
                row["decision"] = "yes"
            elif row.get("decision") == "reject":
                row["decision"] = "no"
        json_response(handler, 200, {"ok": True, "clip": row, "mode": "youtube"})
        return

    try:
        row = update_train_label(clip_id=cid, url=url, decision=decision, notes=notes)
    except ValueError as e:
        json_response(handler, 400, {"ok": False, "error": str(e)})
        return
    except KeyError:
        json_response(handler, 404, {"ok": False, "error": "clip not found"})
        return
    json_response(handler, 200, {"ok": True, "clip": row})


def handle_post_scan(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """Enqueue training clips into the Pathé scrape queue and start scoring."""
    init_db()
    body = body if isinstance(body, dict) else {}
    query = str(body.get("query") or DEFAULT_TRAIN_QUERY).strip()
    if not query:
        json_response(handler, 400, {"ok": False, "error": "missing Pathé search query"})
        return
    only = str(body.get("only") or "all").strip().lower()
    if only == "yes":
        status = "yes"
    elif only in ("pending", "unlabeled"):
        status = "pending"
    else:
        status = ""
    data = list_train_clips(query=query, status=status, limit=5000, offset=0)
    clips = data.get("clips") or []
    items = [
        {
            "url": c.get("url"),
            "title": c.get("title") or f"Asset {c.get('asset_id')}",
            "year": c.get("year") or "",
            "identifier": c.get("asset_id") or "",
            "source": "British Pathé",
            "downloadable": "yes",
        }
        for c in clips
        if c.get("url")
    ]
    if not items:
        json_response(
            handler,
            400,
            {"ok": False, "error": "no clips to scan — load the Pathé search first"},
        )
        return
    from pipeline_pathe import start_pathe_scrape

    inserted = insert_queue_items(items, hub_url="britishpathe.com")
    scrape = start_pathe_scrape(max_videos="all", workers=body.get("workers"))
    json_response(
        handler,
        200 if scrape.get("ok") else 409,
        {
            "ok": bool(scrape.get("ok")),
            "queued": inserted,
            "n_clips": len(items),
            "scrape": scrape,
        },
    )


def handle_post_clip(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """Export Keep/Pass stills and train frozen-CLIP linear probe.

    Body:
      ``{"deep": true}`` deep-sample then train (default when export).
      ``{"export": false}`` train existing dataset only (respects exclusions).
    """
    from clip_ft import start_clip_ft_job

    deep = True
    export = True
    if isinstance(body, dict):
        if "deep" in body:
            deep = bool(body.get("deep"))
        if "export" in body:
            export = bool(body.get("export"))
        # Probe UI sends deep:false meaning "don't re-export"
        if body.get("deep") is False and "export" not in body:
            export = False
    result = start_clip_ft_job(deep=deep, export=export)
    code = 200 if result.get("ok") else 409
    json_response(handler, code, result)
