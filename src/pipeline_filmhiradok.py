"""Filmhíradók Online discover (catalog crawl) + scrape delegation.

Discover walks `search.php?page=N&q=` (empty query = full ~23k catalog) and
enqueues every segment as `fho:segment` rows keyed by their watch.php URL.
Scrape reuses the shared RunPod/local video pipeline; the filmhiradok resolver
turns each watch page into the full-issue MP4 + segment window just-in-time.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from db import init_db, insert_queue_items, set_job
from filmhiradok import catalog_pages, fetch_search_page

_lock = threading.Lock()
_active = {"discover": False}
_stop = threading.Event()


def is_discover_running() -> bool:
    with _lock:
        return bool(_active["discover"])


def start_discover(
    *,
    query: str = "",
    max_pages: int = 0,
    delay: float = 0.35,
) -> dict[str, Any]:
    with _lock:
        if _active["discover"]:
            return {"ok": False, "error": "busy"}
        _active["discover"] = True
    _stop.clear()

    init_db()
    q = (query or "").strip()
    label = f"“{q}”" if q else "full catalog"
    set_job(
        "fho_discover",
        status="running",
        phase="discover",
        message=f"Filmhíradók discover · {label}…",
        progress=2,
        error="",
        completed=0,
        total=0,
    )

    def _run() -> None:
        added = 0
        skipped = 0
        page = 0
        n_pages = 1
        total_found = 0
        try:
            while page < n_pages and not _stop.is_set():
                items, total = fetch_search_page(page, q)
                if total:
                    total_found = total
                    n_pages = catalog_pages(total)
                    if max_pages > 0:
                        n_pages = min(n_pages, int(max_pages))
                rows = [
                    {
                        "url": it["url"],
                        "title": it["title"],
                        "year": it.get("year") or "",
                        "source": "fho:segment",
                        "downloadable": "yes",
                        "hub_url": "fho",
                    }
                    for it in items
                ]
                stats = insert_queue_items(rows, hub_url="fho")
                added += int(stats.get("n_added") or 0)
                skipped += int(stats.get("n_skipped") or 0)
                set_job(
                    "fho_discover",
                    message=(
                        f"page {page + 1}/{n_pages} · +{stats.get('n_added', 0)} new · "
                        f"{added} queued of {total_found or '?'}"
                    ),
                    progress=min(99.0, 100.0 * (page + 1) / max(n_pages, 1)),
                    completed=added,
                    total=int(total_found or 0),
                )
                page += 1
                if not items:
                    break
                if page < n_pages and not _stop.is_set():
                    time.sleep(max(0.0, float(delay)))
            stopped = _stop.is_set() and page < n_pages
            set_job(
                "fho_discover",
                status="idle" if stopped else "done",
                phase="stopped" if stopped else "done",
                progress=100,
                message=(
                    f"Stopped at page {page}/{n_pages} · {added} queued"
                    if stopped
                    else f"Discover done · {added} new · {skipped} dupes · catalog {total_found}"
                ),
                completed=added,
                total=int(total_found or 0),
            )
        except Exception as e:
            set_job(
                "fho_discover",
                status="error",
                phase="error",
                progress=100,
                error=str(e)[:600],
                message=f"discover failed at page {page + 1}: {e}"[:400],
                completed=added,
            )
        finally:
            with _lock:
                _active["discover"] = False

    threading.Thread(target=_run, daemon=True, name="fho-discover").start()
    return {"ok": True, "job": "fho_discover"}


def stop_discover(*, message: str = "stopped by user") -> dict[str, Any]:
    _stop.set()
    return {"ok": True}


def start_scrape(
    *,
    max_videos: int | str = "all",
    workers: int = 2,
) -> dict[str, Any]:
    from pipeline_scrape import start_scrape as _start

    return _start(max_videos=max_videos, workers=workers, source="fho")


def stop_scrape(*, message: str = "Filmhíradók scrape stopped") -> dict[str, Any]:
    from pipeline_scrape import stop_scrape as _stop_scrape

    return _stop_scrape(message=message)
