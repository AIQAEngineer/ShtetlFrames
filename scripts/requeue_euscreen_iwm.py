#!/usr/bin/env python
"""Re-queue Europeana rows that failed on broken/blocked provider pages.

The running scrape marks euscreen.eu / iwm.org.uk rows status='error' because
yt-dlp's EUScreen extractor is broken and IWM is Cloudflare-blocked. This
script (SAFE to run mid-scrape: only touches status='error' rows):

  1. selects queue_items with status='error' on those hosts,
  2. resolves each item-page URL to a direct media URL via
     provider_resolvers (cache: data/europeana/provider_resolve.jsonl,
     so re-runs are resumable/idempotent),
  3. rewrites queue_items.url to the direct media URL and flips the row back
     to status='pending' with error/detail cleared.

Flags:
  --dry-run          report counts, no DB writes, no cache writes
  --keep-item-urls   don't rewrite url (just flip status; download_entry /
                     process_video_remote re-resolve just-in-time — use this if
                     the queue will sit idle, since noterik tickets may expire)
  --host NAME        only one host (euscreen | iwm)
  --workers N        concurrent resolves (default 8)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from db import db  # noqa: E402

CACHE_PATH = Path(ROOT) / "data" / "europeana" / "provider_resolve.jsonl"
_cache: dict[str, str] = {}
_cache_lock = threading.Lock()
_db_lock = threading.Lock()

_HOST_SQL = {
    "euscreen": "url LIKE '%euscreen.eu%item.html%'",
    "iwm": "url LIKE '%iwm.org.uk%/collections/item/%'",
}


def _load_cache() -> None:
    if not CACHE_PATH.exists():
        return
    with CACHE_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            u, r = rec.get("url"), rec.get("resolved")
            if u and r is not None:
                _cache[u] = r


def _append_cache(url: str, resolved: str) -> None:
    with _cache_lock:
        _cache[url] = resolved
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"url": url, "resolved": resolved}) + "\n")


def _resolve(url: str) -> str:
    from provider_resolvers import resolve_media_url

    cached = _cache.get(url)
    if cached is not None:
        return cached
    resolved = resolve_media_url(url) or "FAIL"
    _append_cache(url, resolved)
    return resolved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-item-urls", action="store_true")
    ap.add_argument("--host", choices=["euscreen", "iwm"], default=None)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    _load_cache()
    hosts = [args.host] if args.host else list(_HOST_SQL)
    where = " OR ".join(_HOST_SQL[h] for h in hosts)
    with db() as conn:
        rows = conn.execute(
            f"SELECT id, url FROM queue_items WHERE status='error' AND ({where})"
        ).fetchall()
    print(f"error rows on {hosts}: {len(rows)}")

    results: dict[int, tuple[str, str]] = {}  # id -> (item_url, resolved)
    fails = 0
    todo = [(r["id"], r["url"]) for r in rows]

    def work(rid: int, url: str) -> tuple[int, str, str]:
        return rid, url, _resolve(url)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(work, rid, url) for rid, url in todo]
        done = 0
        for fut in as_completed(futs):
            rid, url, resolved = fut.result()
            done += 1
            if resolved == "FAIL":
                fails += 1
            else:
                results[rid] = (url, resolved)
            if done % 250 == 0 or done == len(todo):
                print(f"resolved {done}/{len(todo)} (fails: {fails})", flush=True)

    print(f"resolved OK: {len(results)}, failed: {fails}")
    if args.dry_run:
        print("dry-run: no DB updates applied")
        return 0

    updated = skipped = 0
    with _db_lock, db(write=True) as conn:
        for rid, (item_url, resolved) in results.items():
            try:
                if args.keep_item_urls:
                    cur = conn.execute(
                        "UPDATE queue_items SET status='pending', error='', detail='' "
                        "WHERE id=? AND status='error'",
                        (rid,),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE queue_items SET url=?, status='pending', error='', detail='' "
                        "WHERE id=? AND status='error'",
                        (resolved, rid),
                    )
                updated += int(cur.rowcount or 0)
            except Exception as e:  # UNIQUE collision on rewritten url, etc.
                skipped += 1
                print(f"skip id={rid}: {e}"[:160])
    print(f"re-queued {updated} rows (skipped {skipped}); {fails} still error")
    return 0


if __name__ == "__main__":
    sys.exit(main())
