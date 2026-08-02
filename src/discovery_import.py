"""Import EFG + Europeana discovery CSVs into the shared scrape queue.

Turns discovery rows into `queue_items` so the existing local scrape
(download_entry → scan_video → insert_candidates) can scan them and surface
hits in the Review workspace.

URL strategy per source:
- EFG embedded  -> direct MP4/HLS stream_url (download_entry handles direct
  video; HLS/INA fall through to yt-dlp).
- EFG youtube   -> youtube stream_url (yt-dlp).
- EFG ina       -> INA resourceUrl MP4.
- EFG linked_out-> provider page URL when a local resolver or yt-dlp-native
  host covers it (IWM, filmportal, EYE, Vimeo, NLS, …); otherwise skipped.
- Europeana     -> needs a per-item resolve to edmIsShownBy / provider media;
  we store the Europeana item API url and resolve at import time.

Reads (whichever exist):
  output/efg_discovery_pre1950.csv
  output/efg_discovery.csv
  output/europeana_discovery_1980.csv
"""

from __future__ import annotations

import csv
import html as htmlmod
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import DATA_DIR, OUTPUT_DIR
from db import init_db, insert_queue_items, queue_stats

EFG_CSVS = [
    OUTPUT_DIR / "efg_discovery_pre1950.csv",
    OUTPUT_DIR / "efg_discovery.csv",
]
EUROPEANA_CSV = OUTPUT_DIR / "europeana_discovery_1980.csv"

DOWNLOADABLE_KINDS = {"embedded", "youtube", "ina", "linked_out"}

# Embedded CDNs that must never enter the scrape queue.
_DEAD_EMBED_MARKERS = (
    "videocinecitta.bytewise.it",
    "bytewise.it",
    "repozytorium.fn.org.pl",
    "fn.org.pl",
)


def _is_dead_embed_url(url: str) -> bool:
    u = (url or "").lower()
    return any(m in u for m in _DEAD_EMBED_MARKERS)


def _is_direct_video(url: str) -> bool:
    u = (url or "").lower()
    return ".mp4" in u or u.endswith((".mp4", ".m4v", ".mov", ".webm"))


def efg_rows() -> list[dict]:
    from provider_resolvers import can_import_provider_page

    out: list[dict] = []
    seen: set[str] = set()
    for path in EFG_CSVS:
        if not path.exists():
            continue
        for r in csv.DictReader(path.open(encoding="utf-8")):
            kind = (r.get("kind") or "").strip().lower()
            if kind not in DOWNLOADABLE_KINDS:
                continue
            rid = (r.get("record_id") or "").strip()
            if rid and rid in seen:
                continue

            if kind == "linked_out":
                url = htmlmod.unescape((r.get("external_url") or "").strip())
                if not url or not can_import_provider_page(url):
                    continue
                source = "efg:linked_out"
            else:
                url = htmlmod.unescape((r.get("stream_url") or "").strip())
                if not url or _is_dead_embed_url(url):
                    continue
                source = f"efg:{kind}"

            if rid:
                seen.add(rid)
            title = (r.get("title") or rid or "efg video").strip()
            year = (r.get("year") or "").strip()
            detail = (r.get("detail_url") or "").strip()
            out.append({
                "url": url,
                "title": f"[EFG] {title}"[:300],
                "year": year,
                "source": source,
                "downloadable": "yes",
                "hub_url": detail or "efg",
            })
    return out


_EUROPEANA_RESOLVE_JSONL = DATA_DIR / "europeana" / "resolve_media.jsonl"
_EUROPEANA_RESOLVE_CACHE: dict[str, str] = {}
_RESOLVE_WRITE_LOCK = threading.Lock()


def _load_europeana_cache() -> dict[str, str]:
    """Durable per-record media-URL checkpoint, so a big import is resumable."""
    global _EUROPEANA_RESOLVE_CACHE
    if _EUROPEANA_RESOLVE_CACHE:
        return _EUROPEANA_RESOLVE_CACHE
    if _EUROPEANA_RESOLVE_JSONL.exists():
        for line in _EUROPEANA_RESOLVE_JSONL.open(encoding="utf-8"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                _EUROPEANA_RESOLVE_CACHE[d["rid"]] = d.get("url") or ""
            except Exception:
                continue
    return _EUROPEANA_RESOLVE_CACHE


def _append_europeana_cache(rid: str, url: str) -> None:
    _EUROPEANA_RESOLVE_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with _RESOLVE_WRITE_LOCK:
        with _EUROPEANA_RESOLVE_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"rid": rid, "url": url}, ensure_ascii=False) + "\n")


def _api_key() -> str:
    return (os.environ.get("EUROPEANA_API_KEY") or os.environ.get("EUROPEANA_KEY") or "").strip()


def _resolve_one(record_id: str, shown_at: str, key: str, *, retries: int = 3) -> tuple[str, str]:
    """Resolve one Europeana record to a playable media URL.

    Order: video/* webResource -> edmIsShownBy -> edmObject -> edmIsShownAt.
    Backs off on HTTP 429 like the discovery crawler did.
    """
    rid = (record_id or "").strip()
    url = ""
    if rid and key:
        api = f"https://api.europeana.eu/record/v2{rid}.json?wskey={urllib.parse.quote(key)}&profile=rich"
        for attempt in range(retries):
            try:
                req = urllib.request.Request(api, headers={"User-Agent": "ShtetlFrames/1.0 (europeana-resolve)"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8", "replace"))
                aggs = (data.get("object") or {}).get("aggregations") or []
                for agg in aggs:
                    for wr in agg.get("webResources") or []:
                        mt = wr.get("ebucoreHasMimeType") or ""
                        about = wr.get("about") or ""
                        if str(about).startswith("http") and str(mt).startswith("video"):
                            url = str(about)
                            break
                    if url:
                        break
                    cand = agg.get("edmIsShownBy") or agg.get("edmObject") or ""
                    if isinstance(cand, list):
                        cand = cand[0] if cand else ""
                    if cand and str(cand).startswith("http"):
                        url = str(cand)
                        break
                break
            except urllib.error.HTTPError as e:
                if int(e.code or 0) == 429 and attempt < retries - 1:
                    time.sleep(20 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    if not url:
        url = (shown_at or "").strip()
    return rid, url


def europeana_rows(*, resolve: bool = True, limit_resolve: int = 0, on_progress=None, workers: int = 16) -> list[dict]:
    out: list[dict] = []
    if not EUROPEANA_CSV.exists():
        return out
    rows_in = list(csv.DictReader(EUROPEANA_CSV.open(encoding="utf-8")))
    if not resolve:
        for r in rows_in:
            url = (r.get("edm_is_shown_at") or "").strip()
            if not url:
                continue
            title = (r.get("title") or r.get("record_id") or "europeana video").strip()
            provider = (r.get("provider_name") or "").strip()
            out.append({
                "url": url,
                "title": f"[EU] {title}"[:300],
                "year": str(r.get("year") or "").strip(),
                "source": f"europeana:{provider[:40]}" if provider else "europeana",
                "downloadable": "yes",
                "hub_url": (r.get("europeana_url") or "").strip() or "europeana",
            })
        return out

    cache = _load_europeana_cache()
    pending: list[tuple[str, str]] = []
    seen_pending: set[str] = set()
    for r in rows_in:
        rid = (r.get("record_id") or "").strip()
        shown_at = (r.get("edm_is_shown_at") or "").strip()
        if rid and rid not in cache and rid not in seen_pending:
            seen_pending.add(rid)
            pending.append((rid, shown_at))
    if limit_resolve:
        pending = pending[:limit_resolve]

    if pending and on_progress:
        on_progress(f"Resolving Europeana media… 0/{len(pending)} ({len(cache)} cached)")

    key = _api_key()
    done = 0
    prog_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(_resolve_one, rid, shown_at, key) for rid, shown_at in pending]
        for fut in as_completed(futs):
            rid, url = fut.result()
            cache[rid] = url
            _append_europeana_cache(rid, url)
            with prog_lock:
                done += 1
                if on_progress and (done % 200 == 0 or done == len(pending)):
                    on_progress(f"Resolving Europeana media… {done}/{len(pending)}")

    for r in rows_in:
        rid = (r.get("record_id") or "").strip()
        url = cache.get(rid) or (r.get("edm_is_shown_at") or "").strip()
        if not url:
            continue
        title = (r.get("title") or rid or "europeana video").strip()
        provider = (r.get("provider_name") or "").strip()
        out.append({
            "url": url,
            "title": f"[EU] {title}"[:300],
            "year": str(r.get("year") or "").strip(),
            "source": f"europeana:{provider[:40]}" if provider else "europeana",
            "downloadable": "yes",
            "hub_url": (r.get("europeana_url") or "").strip() or "europeana",
        })
    return out


def import_into_queue(
    *,
    include_efg: bool = True,
    include_europeana: bool = True,
    resolve_europeana: bool = True,
    europeana_limit: int = 0,
    on_progress=None,
) -> dict:
    init_db()
    items: list[dict] = []
    if include_efg:
        if on_progress:
            on_progress("Reading EFG CSV…")
        items.extend(efg_rows())
    if include_europeana:
        if on_progress:
            on_progress("Reading + resolving Europeana CSV…")
        items.extend(europeana_rows(resolve=resolve_europeana, limit_resolve=europeana_limit, on_progress=on_progress))
    if on_progress:
        on_progress(f"Inserting {len(items)} into queue…")
    res = insert_queue_items(items)
    return {
        "ok": True,
        "attempted": len(items),
        **res,
        **queue_stats(),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--no-efg", action="store_true")
    ap.add_argument("--no-europeana", action="store_true")
    ap.add_argument("--no-resolve", action="store_true", help="skip Europeana per-item resolve")
    ap.add_argument("--europeana-limit", type=int, default=0)
    args = ap.parse_args()
    out = import_into_queue(
        include_efg=not args.no_efg,
        include_europeana=not args.no_europeana,
        resolve_europeana=not args.no_resolve,
        europeana_limit=args.europeana_limit,
    )
    print(json.dumps(out, indent=2))
