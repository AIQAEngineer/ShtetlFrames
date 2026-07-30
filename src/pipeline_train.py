"""Seed Pathé search / YouTube reference videos into Orthodox training labels."""

from __future__ import annotations

import json
import re
import threading
import time
import traceback
from typing import Any

from config import OUTPUT_DIR
from db import get_job, init_db, set_job, update_train_thumbs, upsert_train_clips

_lock = threading.Lock()
_active = False
_thumb_lock = threading.Lock()
_thumb_active = False
_yt_watch_lock = threading.Lock()
_yt_watch_active = False
_yt_local_lock = threading.Lock()
_yt_local_active = False

# Empty default — set a Pathé searchQuery when seeding (UI / API).
DEFAULT_TRAIN_QUERY = ""
DEFAULT_TRAIN_MAX = 500
_YT_REF_PATH = OUTPUT_DIR / "train_yt_ref.json"
_TRAIN_NOTE = "train:orthodox_ref"
_YT_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{6,})",
    re.I,
)


def train_seed_busy() -> bool:
    with _lock:
        return _active


def start_train_seed(
    *,
    query: str = DEFAULT_TRAIN_QUERY,
    max_items: int = DEFAULT_TRAIN_MAX,
    resume: bool = True,
) -> dict:
    """Background-fetch Pathé search listing into ``train_clips``."""
    global _active
    init_db()
    q = (query or DEFAULT_TRAIN_QUERY).strip()
    if not q:
        return {"ok": False, "error": "missing Pathé search query"}
    try:
        cap = max(1, min(int(max_items or DEFAULT_TRAIN_MAX), 5000))
    except (TypeError, ValueError):
        cap = DEFAULT_TRAIN_MAX

    with _lock:
        if _active:
            return {"ok": False, "error": "train seed already running", "job": get_job("train_seed")}
        _active = True

    set_job(
        "train_seed",
        status="running",
        phase="discover",
        message=f"Loading Pathé search “{q}”…",
        progress=2,
        discovered=0,
        total=cap,
        completed=0,
        hits=0,
        error="",
    )

    def _run() -> None:
        global _active
        added = 0
        try:
            from britishpathe import discover_catalog

            def on_status(msg: str) -> None:
                set_job("train_seed", message=str(msg)[:200])

            def on_batch(rows: list[dict]) -> None:
                nonlocal added
                stats = upsert_train_clips(rows, query=q)
                added += int(stats.get("n_added") or 0)
                set_job(
                    "train_seed",
                    discovered=added,
                    completed=added,
                    progress=min(95, 5 + 90 * added / max(1, cap)),
                    message=f"Training set · {added:,} clips from “{q}”…",
                )

            out = discover_catalog(
                query=q,
                max_items=cap,
                on_status=on_status,
                on_batch=on_batch,
                resume=bool(resume),
            )
            n_found = int(out.get("n_total") or out.get("n") or added or 0)
            set_job(
                "train_seed",
                status="done",
                phase="done",
                progress=100,
                discovered=added,
                completed=added,
                message=f"Ready · {added:,} new clips for “{q}” (listing {n_found:,})",
            )
        except Exception as e:
            set_job(
                "train_seed",
                status="error",
                phase="error",
                message=str(e)[:200],
                error=traceback.format_exc()[-1200:],
                progress=100,
            )
        finally:
            with _lock:
                _active = False

    threading.Thread(target=_run, daemon=True, name="train-seed").start()
    return {"ok": True, "job": get_job("train_seed"), "query": q, "max_items": cap}


def backfill_train_thumbs(
    *,
    query: str = DEFAULT_TRAIN_QUERY,
    max_pages: int = 8,
) -> dict:
    """Re-fetch Pathé listing pages and fill missing train_clips.thumb_url."""
    global _thumb_active
    init_db()
    q = (query or DEFAULT_TRAIN_QUERY).strip()
    if not q:
        return {"ok": False, "error": "missing Pathé search query", "updated": 0}
    with _thumb_lock:
        if _thumb_active:
            return {"ok": False, "error": "thumb backfill already running", "updated": 0}
        _thumb_active = True
    updated = 0
    pages = 0
    try:
        from britishpathe import fetch_search_assets, search_url
        from db import list_train_clips

        stats = list_train_clips(query=q, limit=1).get("stats") or {}
        if int(stats.get("n_total") or 0) <= 0:
            return {"ok": True, "updated": 0, "pages": 0, "query": q}

        # Cover enough listing pages for the current set (~20 assets/page).
        need = max(1, min(int(max_pages or 8), 40))
        for page in range(1, need + 1):
            url = search_url(q, page=page)
            try:
                batch = fetch_search_assets(url)
            except Exception:
                break
            pages += 1
            if not batch:
                break
            updated += update_train_thumbs(batch)
            from db import db as _db

            with _db() as conn:
                missing = conn.execute(
                    "SELECT COUNT(*) AS n FROM train_clips "
                    "WHERE query=? AND (thumb_url IS NULL OR thumb_url='')",
                    (q,),
                ).fetchone()["n"]
            if int(missing or 0) <= 0:
                break
        return {"ok": True, "updated": updated, "pages": pages, "query": q}
    finally:
        with _thumb_lock:
            _thumb_active = False


def youtube_video_id(url: str) -> str | None:
    m = _YT_ID_RE.search(url or "")
    return m.group(1) if m else None


def save_youtube_train_ref(url: str, *, title: str = "") -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    vid = youtube_video_id(url)
    if not vid:
        raise ValueError("not a YouTube watch URL")
    payload = {
        "url": (url or "").strip(),
        "video_id": vid,
        "title": (title or "").strip(),
        "updated_at": time.time(),
    }
    _YT_REF_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_youtube_train_ref() -> dict[str, Any] | None:
    try:
        if not _YT_REF_PATH.is_file():
            return None
        data = json.loads(_YT_REF_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("url") else None
    except Exception:
        return None


def clear_youtube_train_ref() -> None:
    try:
        if _YT_REF_PATH.is_file():
            _YT_REF_PATH.unlink()
    except Exception:
        pass


def _auto_accept_youtube_ref_candidates(ref: dict[str, Any]) -> int:
    """Mark unscored hits from the reference video as Orthodox Keep for few-shot."""
    from db import db, update_review

    url = (ref.get("url") or "").strip()
    vid = (ref.get("video_id") or "").strip()
    if not url and not vid:
        return 0
    with db() as conn:
        rows = conn.execute(
            """SELECT id, decision, notes, source_url FROM candidates
               WHERE (source_url LIKE ? OR source_url LIKE ?)
               ORDER BY id DESC LIMIT 500""",
            (f"%{vid}%", f"%{url}%"),
        ).fetchall()
    n = 0
    for r in rows:
        d = dict(r)
        dec = (d.get("decision") or "").strip()
        notes = str(d.get("notes") or "")
        if dec and _TRAIN_NOTE not in notes.lower():
            # Human already labeled something else — leave it.
            continue
        if dec == "accept" and _TRAIN_NOTE in notes.lower():
            continue
        new_notes = notes
        if _TRAIN_NOTE not in notes.lower():
            new_notes = f"{_TRAIN_NOTE}\n{notes}".strip()
        update_review(int(d["id"]), "accept", new_notes)
        n += 1
    return n


def _start_youtube_ref_watcher(ref: dict[str, Any]) -> None:
    global _yt_watch_active
    with _yt_watch_lock:
        if _yt_watch_active:
            return
        _yt_watch_active = True

    def _run() -> None:
        global _yt_watch_active
        try:
            # Poll while scrape may still be producing hits.
            for _ in range(240):  # ~20 min
                try:
                    _auto_accept_youtube_ref_candidates(ref)
                except Exception:
                    pass
                scrape = get_job("scrape") or {}
                if str(scrape.get("status") or "") not in ("running",) and _ > 12:
                    # One last pass after scrape settles.
                    try:
                        _auto_accept_youtube_ref_candidates(ref)
                    except Exception:
                        pass
                    break
                time.sleep(5.0)
        finally:
            with _yt_watch_lock:
                _yt_watch_active = False

    threading.Thread(target=_run, daemon=True, name="train-yt-ref-watch").start()


def _train_dbg(hypothesis_id: str, location: str, message: str, **data: Any) -> None:
    # #region agent log
    from logutil import agent_dbg

    agent_dbg(hypothesis_id, location, message, data, run_id="yt-train-gpu", post=True)
    # #endregion


def _start_youtube_gpu_scan(watch: str, ref: dict[str, Any]) -> dict[str, Any]:
    """Scan one YouTube reference on RunPod GPU (1 pod — never waits for a full fleet)."""
    global _yt_local_active
    with _yt_local_lock:
        if _yt_local_active:
            return {"ok": False, "error": "youtube_scan_running"}
        _yt_local_active = True

    vid = (ref.get("video_id") or youtube_video_id(watch) or "").strip()
    # #region agent log
    _train_dbg("H1", "pipeline_train.py:_start_youtube_gpu_scan", "enter", video_id=vid)
    # #endregion

    def _run() -> None:
        global _yt_local_active
        hits = 0
        try:
            from db import db
            from pipeline_scrape import _safe_queue_status
            from runpod_client import get_pod_pool, set_pod_pool
            from runpod_provision import (
                ensure_pods,
                set_pod_create_ceiling,
                set_pod_creates_blocked,
                trim_shtetl_pods,
            )

            with db() as conn:
                row = conn.execute(
                    "SELECT * FROM queue_items WHERE url=?", (watch,)
                ).fetchone()
            if row is None:
                raise RuntimeError("queue row missing after prioritize")
            row_d = dict(row)
            qid = int(row_d["id"])

            set_job(
                "train_seed",
                status="running",
                phase="youtube_gpu",
                message=f"Spinning up 1 GPU pod for {vid}…",
                progress=15,
                hub_url=watch,
                error="",
            )
            # One video = one GPU. Cap creates so heal/scrape cannot fleet up.
            set_pod_creates_blocked(False)
            set_pod_create_ceiling(1)
            pool_before = get_pod_pool()
            # #region agent log
            _train_dbg(
                "H2",
                "pipeline_train.py:_start_youtube_gpu_scan",
                "ensure_pods_enter",
                pool_before=len(pool_before),
                creates_blocked=False,
                count=1,
                create_ceiling=1,
            )
            # #endregion

            def on_status(msg: str) -> None:
                set_job("train_seed", message=str(msg)[:200], phase="youtube_gpu")

            t0 = time.time()
            # Kill leftover fleet from prior scrape heal (train only needs 1).
            try:
                trimmed = trim_shtetl_pods(keep=1, on_status=on_status)
            except Exception:
                trimmed = 0
            bases = ensure_pods(
                count=1,
                on_status=on_status,
                min_ready=1,
                extra_fill_sec=0,
            )
            # ensure_pods returns every healthy GPU — pin pool to ONE for train (H7).
            one = [bases[0]] if bases else []
            set_pod_pool(one)
            # #region agent log
            _train_dbg(
                "H7",
                "pipeline_train.py:_start_youtube_gpu_scan",
                "ensure_pods_exit",
                bases_returned=len(bases or []),
                pool_pinned=len(one),
                trimmed=trimmed,
                elapsed_s=round(time.time() - t0, 1),
                base_tails=[(b or "")[-28:] for b in one[:1]],
            )
            # #endregion
            if not one:
                raise RuntimeError("ensure_pods returned no GPU proxies")

            set_job(
                "train_seed",
                status="running",
                phase="youtube_gpu",
                message=f"GPU ready — scanning {vid}…",
                progress=35,
                hub_url=watch,
            )
            _safe_queue_status(qid, "scanning", error="", detail="gpu train scan")
            # #region agent log
            _train_dbg(
                "H4",
                "pipeline_train.py:_start_youtube_gpu_scan",
                "process_start",
                qid=qid,
                backend="runpod",
                train_keep_all=True,
            )
            # #endregion
            # Train: residential proxy, softer CLIP gate, no VLM drop — keep every segment.
            from runpod_client import (
                _push_handlers_best_effort,
                process_video_remote,
                segments_to_candidate_rows,
            )
            from db import insert_candidates

            try:
                _push_handlers_best_effort(one)
            except Exception:
                pass
            out = process_video_remote(
                url=watch,
                title=str(row_d.get("title") or "Orthodox look training reference"),
                queue_id=qid,
                sample_fps=1.5,
                score_threshold=0.02,
                source_url=watch,
                on_status=on_status,
                max_attempts=4,
                force_proxy=True,
                attach_verify=False,
            )
            # #region agent log
            _train_dbg(
                "H8",
                "pipeline_train.py:_start_youtube_gpu_scan",
                "remote_result",
                qid=qid,
                n_segments=len(out.get("segments") or []),
                n_frame_hits=out.get("n_frame_hits"),
                n_hits=out.get("n_hits"),
                error=(out.get("error") or "")[:160],
                top_n=len(out.get("top_frames") or []),
            )
            # #endregion
            rows = segments_to_candidate_rows(out, source_url=watch)
            if rows:
                insert_candidates(rows)
            hits = len(rows)
            _safe_queue_status(qid, "done", error="", detail=f"{hits} hit segment(s)")
            accepted = _auto_accept_youtube_ref_candidates(ref)
            # #region agent log
            _train_dbg(
                "H5",
                "pipeline_train.py:_start_youtube_gpu_scan",
                "process_done",
                qid=qid,
                hits=hits,
                accepted=accepted,
            )
            # #endregion
            set_job(
                "train_seed",
                status="done",
                phase="done",
                message=(
                    f"GPU scan done · {hits} hit(s) · {accepted} tagged for Orthodox training"
                ),
                progress=100,
                hits=hits,
                completed=1,
                hub_url=watch,
            )
        except Exception as e:
            # #region agent log
            _train_dbg(
                "H2",
                "pipeline_train.py:_start_youtube_gpu_scan",
                "error",
                err=str(e)[:240],
            )
            # #endregion
            set_job(
                "train_seed",
                status="error",
                phase="error",
                message=str(e)[:200],
                error=traceback.format_exc()[-1200:],
                progress=100,
                hub_url=watch,
            )
        finally:
            try:
                from runpod_provision import set_pod_create_ceiling

                # Allow Pathé/scrape fleet again after this one-video job.
                set_pod_create_ceiling(None)
            except Exception:
                pass
            with _yt_local_lock:
                _yt_local_active = False

    threading.Thread(target=_run, daemon=True, name="yt-gpu-scan").start()
    return {"ok": True, "backend": "runpod", "deferred": True, "video_id": vid}


def start_youtube_train_ref(url: str, *, title: str = "") -> dict:
    """Queue + GPU-scan a YouTube video as Orthodox positive few-shot training."""
    init_db()
    u = (url or "").strip()
    vid = youtube_video_id(u)
    if not vid:
        return {"ok": False, "error": "need a YouTube watch URL"}
    watch = f"https://www.youtube.com/watch?v={vid}"
    ref = save_youtube_train_ref(watch, title=title or "Orthodox look reference")

    from pipeline_scrape import prioritize_queue_url

    pri = prioritize_queue_url(
        watch, title=title or "Orthodox look training reference"
    )
    # #region agent log
    _train_dbg(
        "H1",
        "pipeline_train.py:start_youtube_train_ref",
        "start",
        video_id=vid,
        priority_status=pri.get("status"),
        scrape_running=pri.get("scrape_running"),
    )
    # #endregion
    scan = _start_youtube_gpu_scan(watch, ref)

    set_job(
        "train_seed",
        status="running",
        phase="youtube_gpu",
        message=f"GPU scan starting · {vid}…",
        progress=10,
        hub_url=watch,
        error="",
    )
    _start_youtube_ref_watcher(ref)
    accepted = _auto_accept_youtube_ref_candidates(ref)
    return {
        "ok": True,
        "ref": ref,
        "priority": pri,
        "scan": scan,
        "auto_accepted": accepted,
    }


def list_youtube_train_candidates(*, limit: int = 500, stats_only: bool = False) -> dict:
    """Candidates from the saved YouTube Orthodox reference video.

    Uses a SQL filter on ``source_url`` — never loads the full candidates table
    (that hung /train while a GPU scan held SQLite).
    """
    from db import db
    from still_store import local_crop_url, local_still_url, local_strip_url

    ref = load_youtube_train_ref()
    empty = {
        "ok": True,
        "ref": None,
        "clips": [],
        "total": 0,
        "stats": {"n_total": 0, "n_pending": 0, "n_yes": 0, "n_no": 0},
    }
    if not ref:
        return empty
    vid = (ref.get("video_id") or "").strip()
    url = (ref.get("url") or "").strip()
    if not vid and not url:
        return {**empty, "ref": ref}
    like_vid = f"%{vid}%" if vid else ""
    like_url = f"%{url}%" if url else ""
    cap = max(1, min(int(limit or 500), 2000))

    # #region agent log
    t0 = time.time()
    # #endregion
    try:
        with db() as conn:
            if like_vid and like_url:
                where = "(source_url LIKE ? OR source_url LIKE ?)"
                params: tuple = (like_vid, like_url)
            elif like_vid:
                where = "source_url LIKE ?"
                params = (like_vid,)
            else:
                where = "source_url LIKE ?"
                params = (like_url,)

            n_total = conn.execute(
                f"SELECT COUNT(*) AS n FROM candidates WHERE {where}", params
            ).fetchone()["n"]
            n_yes = conn.execute(
                f"SELECT COUNT(*) AS n FROM candidates WHERE {where} AND decision='accept'",
                params,
            ).fetchone()["n"]
            n_no = conn.execute(
                f"SELECT COUNT(*) AS n FROM candidates WHERE {where} AND decision='reject'",
                params,
            ).fetchone()["n"]
            n_pending = int(n_total) - int(n_yes) - int(n_no)
            stats = {
                "n_total": int(n_total),
                "n_pending": max(0, n_pending),
                "n_yes": int(n_yes),
                "n_no": int(n_no),
            }
            clips: list[dict] = []
            if not stats_only:
                rows = conn.execute(
                    f"""SELECT * FROM candidates WHERE {where}
                        ORDER BY rank_score DESC LIMIT ?""",
                    (*params, cap),
                ).fetchall()
                for i, r in enumerate(rows, 1):
                    d = dict(r)
                    d["rank"] = i
                    d["key"] = f"{d['id']}"
                    local = local_still_url(d["id"])
                    d["contact_url"] = local
                    d["thumb_url"] = local or ""
                    d["strip_url"] = local_strip_url(d["id"])
                    d["crop_url"] = local_crop_url(d["id"])
                    clips.append(d)
    except Exception as e:
        # #region agent log
        _train_dbg(
            "H8",
            "pipeline_train.py:list_youtube_train_candidates",
            "query_failed",
            err=str(e)[:160],
            ms=int((time.time() - t0) * 1000),
        )
        # #endregion
        return {**empty, "ref": ref, "error": str(e)[:160]}

    # #region agent log
    _train_dbg(
        "H8",
        "pipeline_train.py:list_youtube_train_candidates",
        "ok",
        stats_only=stats_only,
        n_total=stats["n_total"],
        clips=len(clips),
        ms=int((time.time() - t0) * 1000),
    )
    # #endregion
    return {
        "ok": True,
        "ref": ref,
        "clips": clips,
        "total": len(clips) if not stats_only else stats["n_total"],
        "stats": stats,
    }
