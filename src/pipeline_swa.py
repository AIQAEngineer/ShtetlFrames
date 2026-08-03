"""SWA (szukajwarchiwach.gov.pl) still-image discover + parallel CLIP scrape."""

from __future__ import annotations

import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from config import CROPS_DIR, OUTPUT_DIR, load_env
from db import (
    init_db,
    insert_candidates,
    insert_queue_items,
    queue_stats,
    set_job,
    take_pending,
)
from swa import (
    DEFAULT_KEYWORDS,
    SWA_IMAGES_DIR,
    discover_keywords,
    discover_keywords_full,
    download_image,
    resolve_page_images,
    slug_from_url,
)

_lock = threading.Lock()
_active = {"discover": False, "scrape": False}
_scrape_live: dict[int, dict[str, Any]] = {}
_scrape_counts = {"done": 0, "hits": 0, "errors": 0}
_tls = threading.local()


def _models():
    from ultralytics import YOLO

    from shtetl_core.cues import YOLO_WEIGHTS
    from shtetl_core.scoring import CueScorer

    if not getattr(_tls, "ready", False):
        _tls.yolo = YOLO(YOLO_WEIGHTS)
        _tls.scorer = CueScorer()
        _tls.ready = True
    return _tls.yolo, _tls.scorer


def scrape_live_snapshot() -> list[dict[str, Any]]:
    with _lock:
        return [
            {"id": qid, **dict(row)}
            for qid, row in sorted(_scrape_live.items(), key=lambda kv: kv[0])
        ]


def start_discover(
    *,
    keywords: list[str] | None = None,
    max_per_query: int = 40,
    mode: str = "autocomplete",
    max_pages: int = 5,
) -> dict[str, Any]:
    with _lock:
        if _active["discover"] or _active["scrape"]:
            return {"ok": False, "error": "busy"}
        _active["discover"] = True

    init_db()
    terms = keywords or list(DEFAULT_KEYWORDS)
    full = str(mode).strip().lower() == "full"
    set_job(
        "swa_discover",
        status="running",
        phase="discover",
        message=(
            f"SWA {'full-text' if full else 'keyword'} discover · {len(terms)} terms…"
        ),
        progress=5,
        error="",
        completed=0,
        total=len(terms),
    )

    def _run() -> None:
        try:
            def on_status(msg: str) -> None:
                set_job("swa_discover", message=msg[:400])

            if full:
                rows = discover_keywords_full(
                    terms,
                    max_pages=max(1, int(max_pages)),
                    max_per_query=max(1, int(max_per_query)),
                    on_status=on_status,
                )
            else:
                rows = discover_keywords(
                    terms,
                    photos_only=True,
                    max_per_query=max(1, int(max_per_query)),
                    on_status=on_status,
                )
            clean = [
                {
                    "url": r["url"],
                    "title": r.get("title") or r["url"],
                    "year": r.get("year") or "",
                    "source": r.get("source") or "swa:photo",
                    "downloadable": "yes",
                    "hub_url": r.get("hub_url") or r.get("_page_url") or "swa",
                }
                for r in rows
            ]
            stats = insert_queue_items(clean, hub_url="swa")
            set_job(
                "swa_discover",
                status="done",
                phase="done",
                progress=100,
                message=(
                    f"Discovered {stats.get('n_added', 0)} new · "
                    f"skipped {stats.get('n_skipped', 0)} · "
                    f"from {len(terms)} keywords"
                ),
                completed=int(stats.get("n_added") or 0),
            )
        except Exception as e:
            set_job(
                "swa_discover",
                status="error",
                phase="error",
                progress=100,
                error=str(e)[:600],
                message=f"discover failed: {e}"[:400],
            )
        finally:
            with _lock:
                _active["discover"] = False

    threading.Thread(target=_run, daemon=True, name="swa-discover").start()
    return {"ok": True, "job": "swa_discover"}


def start_scrape(
    *,
    max_images: int | str = "all",
    workers: int = 4,
) -> dict[str, Any]:
    with _lock:
        if _active["discover"] or _active["scrape"]:
            return {"ok": False, "error": "busy"}
        _active["scrape"] = True
        _scrape_live.clear()
        _scrape_counts["done"] = 0
        _scrape_counts["hits"] = 0
        _scrape_counts["errors"] = 0

    init_db()
    load_env()
    try:
        n_workers = max(1, min(int(workers or 4), 16))
    except (TypeError, ValueError):
        n_workers = 4
    if isinstance(max_images, str) and max_images.strip().lower() in ("", "all", "*"):
        limit = None
    else:
        try:
            limit = max(1, int(max_images))
        except (TypeError, ValueError):
            limit = None

    items = take_pending(limit, source="swa")
    set_job(
        "swa_scrape",
        status="running",
        phase="scraping",
        message=f"SWA image scrape · {len(items)} pending · {n_workers} workers",
        progress=0,
        error="",
        completed=0,
        hits=0,
        total=len(items),
        workers=n_workers,
        max_videos=str(max_images),
    )
    if not items:
        set_job(
            "swa_scrape",
            status="done",
            phase="done",
            progress=100,
            message="No pending SWA images",
        )
        with _lock:
            _active["scrape"] = False
        return {"ok": True, "job": "swa_scrape", "queued": 0}

    threading.Thread(
        target=_scrape_job,
        args=(items, n_workers),
        daemon=True,
        name="swa-scrape",
    ).start()
    return {"ok": True, "job": "swa_scrape", "queued": len(items)}


def stop_scrape(*, message: str = "stopped") -> dict[str, Any]:
    with _lock:
        _active["scrape"] = False
        _scrape_live.clear()
    set_job(
        "swa_scrape",
        status="idle",
        phase="stopped",
        progress=100,
        message=message[:400],
    )
    return {"ok": True}


def _scrape_job(items: list[dict], workers: int) -> None:
    from db import set_queue_status

    total = len(items)
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_process_one, row): row for row in items}
            for fut in as_completed(futs):
                row = futs[fut]
                qid = int(row["id"])
                try:
                    n_hits = int(fut.result() or 0)
                    with _lock:
                        _scrape_counts["done"] += 1
                        _scrape_counts["hits"] += n_hits
                        _scrape_live.pop(qid, None)
                        done = _scrape_counts["done"]
                        hits = _scrape_counts["hits"]
                        errors = _scrape_counts["errors"]
                    set_queue_status(qid, "done", detail=f"{n_hits} hit(s)")
                    pct = 100.0 * done / max(total, 1)
                    set_job(
                        "swa_scrape",
                        message=(
                            f"{done}/{total} done · {hits} hits · {errors} err · "
                            f"{len(_scrape_live)} active"
                        ),
                        progress=pct,
                        completed=done,
                        hits=hits,
                    )
                except Exception as e:
                    err = str(e)[:500]
                    with _lock:
                        _scrape_counts["done"] += 1
                        _scrape_counts["errors"] += 1
                        _scrape_live.pop(qid, None)
                        done = _scrape_counts["done"]
                        hits = _scrape_counts["hits"]
                        errors = _scrape_counts["errors"]
                    try:
                        set_queue_status(qid, "error", error=err, detail="")
                    except Exception:
                        pass
                    set_job(
                        "swa_scrape",
                        error=err,
                        message=(
                            f"{done}/{total} done · {hits} hits · {errors} err · "
                            f"{len(_scrape_live)} active"
                        ),
                        progress=100.0 * done / max(total, 1),
                        completed=done,
                        hits=hits,
                    )
        with _lock:
            done = _scrape_counts["done"]
            hits = _scrape_counts["hits"]
            errors = _scrape_counts["errors"]
        set_job(
            "swa_scrape",
            status="done",
            phase="done",
            progress=100,
            message=f"SWA done · {done}/{total} · {hits} hits · {errors} err",
            completed=done,
            hits=hits,
        )
    except Exception as e:
        set_job(
            "swa_scrape",
            status="error",
            phase="error",
            progress=100,
            error=str(e)[:600],
            message=traceback.format_exc()[-400:],
        )
    finally:
        with _lock:
            _active["scrape"] = False
            _scrape_live.clear()


def _process_one(row: dict) -> int:
    from shtetl_core.blur import still_path_is_poor
    from shtetl_core.cues import DEFAULT_SCORE_THRESHOLD
    from shtetl_core.scan import scan_still
    import config as app_config

    qid = int(row["id"])
    title = row.get("title") or "SWA"
    url = (row.get("url") or "").strip()
    page_url = (row.get("hub_url") or "").strip()
    if page_url in ("", "swa") or "szukajwarchiwach.gov.pl" not in page_url:
        page_url = url if "szukajwarchiwach.gov.pl" in url and "photos." not in url else ""
    with _lock:
        _scrape_live[qid] = {
            "title": title,
            "phase": "download",
            "detail": "fetching JPEG…",
            "started": time.time(),
        }

    load_env()
    thr = float(getattr(app_config, "SCORE_THRESHOLD", None) or DEFAULT_SCORE_THRESHOLD)
    SWA_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    slug = slug_from_url(url)
    video_id = f"swa_{slug}"
    dest = SWA_IMAGES_DIR / f"{qid}_{slug}.jpg"

    image_urls = [url]
    # Page URLs (jednostka) — expand to CDN / plik JPEGs.
    if "photos.szukajwarchiwach.gov.pl" not in url and "/o/pliki-api/" not in url:
        with _lock:
            live = _scrape_live.get(qid) or {}
            live.update({"phase": "resolve", "detail": "page → scans…"})
            _scrape_live[qid] = live
        image_urls = resolve_page_images(url) or []
        if not image_urls:
            raise RuntimeError("swa_no_images_on_page")
        page_url = page_url or url

    yolo, scorer = _models()
    crops_dir = CROPS_DIR / "swa" / str(qid)
    crops_dir.mkdir(parents=True, exist_ok=True)
    best_hits = []
    best_still: Path | None = None
    best_score = -1e9
    # Prefer archive page for Review attribution; fall back to CDN JPEG URL.
    source_url = page_url or url
    image_url: str | None = None

    for i, img_url in enumerate(image_urls[:12]):
        with _lock:
            live = _scrape_live.get(qid) or {}
            live.update(
                {
                    "phase": "download",
                    "detail": f"JPEG {i + 1}/{min(len(image_urls), 12)}…",
                }
            )
            _scrape_live[qid] = live
        part = SWA_IMAGES_DIR / f"{qid}_{slug}_{i}.jpg"
        try:
            download_image(img_url, part)
        except Exception as e:
            if i == 0 and len(image_urls) == 1:
                raise
            continue
        if still_path_is_poor(part):
            # Still may be a full archival plate — try scoring anyway if large.
            try:
                import cv2

                im = cv2.imread(str(part))
                if im is None or min(im.shape[:2]) < 240:
                    part.unlink(missing_ok=True)
                    continue
            except Exception:
                part.unlink(missing_ok=True)
                continue
        with _lock:
            live = _scrape_live.get(qid) or {}
            live.update({"phase": "scan", "detail": "YOLO+CLIP…"})
            _scrape_live[qid] = live
        hits = scan_still(
            part,
            video_id=f"{video_id}_{i}",
            scorer=scorer,
            yolo=yolo,
            score_threshold=thr,
            save_crops_dir=crops_dir,
        )
        if not hits:
            continue
        top = hits[0]
        if top.score > best_score:
            best_score = float(top.score)
            best_hits = hits
            best_still = part
            image_url = img_url
            if not page_url:
                source_url = img_url
            # Keep canonical dest copy for Review.
            try:
                shutil.copyfile(part, dest)
            except OSError:
                dest = part

    if not best_hits or best_still is None:
        return 0

    # Prefer full archival plate for Review when the person crop is soft/tiny.
    still_path = best_still
    crop0 = best_hits[0].crop_path
    if crop0 and Path(crop0).is_file() and not still_path_is_poor(Path(crop0)):
        still_path = Path(crop0)

    peak = float(best_hits[0].score)
    mean = float(sum(h.score for h in best_hits) / max(len(best_hits), 1))
    row_out = {
        "video_id": video_id,
        "start_sec": 0.0,
        "end_sec": 0.0,
        "peak_score": round(peak, 4),
        "mean_score": round(mean, 4),
        "rank_score": round(peak, 4),
        "hit_count": len(best_hits),
        "best_cue": best_hits[0].best_cue,
        "source_url": source_url,
        "image_url": image_url,
        "notes": f"swa still · {(title or '')[:80]}",
        "_local_still": str(still_path),
    }
    with _lock:
        live = _scrape_live.get(qid) or {}
        live.update({"phase": "upload", "detail": "writing Review hit…"})
        _scrape_live[qid] = live
    insert_candidates([row_out])
    return 1
