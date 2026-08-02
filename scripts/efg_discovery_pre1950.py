"""EFG discovery: all videos dated before 1950 (no keyword topic filter).

Uses EFG's year+media facets (via Scrapfly JS form submit) and paginates
every result page. Broad seed queries maximize recall; records are deduped
by record_id.

Outputs:
  data/efg/listing_pre1950.json
  data/efg/resolve_pre1950.jsonl
  output/efg_discovery_pre1950.csv
"""

from __future__ import annotations

import csv
import json
import msvcrt
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import DATA_DIR, OUTPUT_DIR
import efg

STATE_DIR = DATA_DIR / "efg"
LISTING_JSON = STATE_DIR / "listing_pre1950.json"
LISTING_PAGES = STATE_DIR / "listing_pre1950_pages.json"  # {query: last_done_page}
RESOLVE_JSONL = STATE_DIR / "resolve_pre1950.jsonl"
OUT_CSV = OUTPUT_DIR / "efg_discovery_pre1950.csv"
LOCK_FILE = STATE_DIR / "discovery_pre1950.lock"

# Largest filtered counts first (measured). Overlap is high; union grows slowly.
SEEDS = ["a", "the", "film", "i", "la", "en", "di", "e", "die", "un", "der", "le", "o", "u", "y"]

LISTING_WORKERS = 8
RESOLVE_WORKERS = 12
PER_PAGE = 10  # EFG default


def single_instance() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_FILE, "a+b")
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("another pre1950 discovery instance is running; exiting", flush=True)
        sys.exit(0)
    globals()["_lock_fh"] = fh


def log(msg: str) -> None:
    print(msg, flush=True)


def _load_listing() -> dict[str, dict]:
    if LISTING_JSON.exists():
        return json.loads(LISTING_JSON.read_text(encoding="utf-8"))
    return {}


def _save_listing(records: dict[str, dict]) -> None:
    tmp = LISTING_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LISTING_JSON)


def _load_page_progress() -> dict[str, set[int]]:
    """Map query -> set of successfully fetched page indices."""
    if not LISTING_PAGES.exists():
        return {}
    raw = json.loads(LISTING_PAGES.read_text(encoding="utf-8"))
    out: dict[str, set[int]] = {}
    for q, v in raw.items():
        if isinstance(v, list):
            out[q] = set(int(x) for x in v)
        elif isinstance(v, int):
            # Legacy format stored only the max page; treat as unknown — force refill.
            out[q] = set()
        else:
            out[q] = set()
    return out


def _save_page_progress(prog: dict[str, set[int]]) -> None:
    serial = {q: sorted(pages) for q, pages in prog.items()}
    LISTING_PAGES.write_text(json.dumps(serial), encoding="utf-8")


def _fetch_page(query: str, page: int, *, attempts: int = 3) -> str:
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return efg.fetch_filtered_search_page(query, page)
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(str(last_err))


def phase_a() -> dict[str, dict]:
    records = _load_listing()
    progress = _load_page_progress()
    log(f"[A] resume: {len(records)} records, pages done="
        f"{{{', '.join(f'{q}:{len(p)}' for q, p in progress.items())}}}")
    lock = threading.Lock()

    def scrape_seed(query: str) -> None:
        done_pages = progress.setdefault(query, set())
        try:
            html0 = _fetch_page(query, 0)
            recs0, last = efg.parse_search_page(html0, query)
            total = efg.parse_result_count(html0)
        except Exception as e:
            log(f"[A] {query!r} p0 FAIL: {str(e)[:140]}")
            return
        if total and total > 0:
            last = max(last, (total + PER_PAGE - 1) // PER_PAGE - 1)
        log(f"[A] {query!r}: total≈{total} last_page={last} already_have={len(done_pages)}")

        def ingest(page: int, recs: list[dict]) -> None:
            with lock:
                for r in recs:
                    y = r.get("year")
                    if y is not None and int(y) >= 1950:
                        continue
                    rid = r["record_id"]
                    if rid in records:
                        qs = records[rid].setdefault("queries", [records[rid].get("query") or query])
                        if query not in qs:
                            qs.append(query)
                    else:
                        r["queries"] = [query]
                        records[rid] = r
                done_pages.add(page)
                if page % 10 == 0 or page == last or len(done_pages) % 25 == 0:
                    _save_listing(records)
                    _save_page_progress(progress)
                    log(f"[A] {query!r} p{page}/{last} have={len(done_pages)} union={len(records)}")

        if 0 not in done_pages:
            ingest(0, recs0)

        missing = [p for p in range(0, last + 1) if p not in done_pages]
        if not missing:
            log(f"[A] {query!r} already complete")
            return
        log(f"[A] {query!r}: fetching {len(missing)} missing pages")

        with ThreadPoolExecutor(max_workers=LISTING_WORKERS) as pool:
            futs = {pool.submit(_fetch_page, query, p): p for p in missing}
            for f in as_completed(futs):
                p = futs[f]
                try:
                    html = f.result()
                    recs, _ = efg.parse_search_page(html, query)
                except Exception as e:
                    log(f"[A] {query!r} p{p}: {str(e)[:120]}")
                    continue
                ingest(p, recs)

        with lock:
            _save_listing(records)
            _save_page_progress(progress)
        log(f"[A] {query!r} done have={len(done_pages)}/{last+1} union={len(records)}")

    for seed in SEEDS:
        scrape_seed(seed)

    _save_listing(records)
    log(f"[A] done: {len(records)} unique pre-1950 records")
    return records


def phase_b(records: dict[str, dict]) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if RESOLVE_JSONL.exists():
        for line in RESOLVE_JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                    done[row["record_id"]] = row
                except Exception:
                    pass
        log(f"[B] resume: {len(done)} already resolved")

    todo = [r for rid, r in records.items() if rid not in done]
    log(f"[B] resolving {len(todo)} with {RESOLVE_WORKERS} workers")
    lock = threading.Lock()
    fh = RESOLVE_JSONL.open("a", encoding="utf-8")
    n = [0]

    def work(rec: dict) -> None:
        res = efg.resolve_record(rec)
        res.pop("queries", None)
        with lock:
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            fh.flush()
            done[res["record_id"]] = res
            n[0] += 1
            if n[0] % 25 == 0 or n[0] == len(todo):
                log(f"[B] {n[0]}/{len(todo)} (total {len(done)})")

    with ThreadPoolExecutor(max_workers=RESOLVE_WORKERS) as pool:
        futs = [pool.submit(work, r) for r in todo]
        for f in as_completed(futs):
            f.result()
    fh.close()
    return done


def write_csv(rows: dict[str, dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "record_id", "kind", "title", "year", "genre", "provider_name",
        "provider_prefix", "stream_url", "external_url", "duration",
        "detail_url", "thumb", "description", "query",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in sorted(rows.values(), key=lambda x: ((x.get("year") or 9999), x["record_id"])):
            w.writerow({
                "record_id": r.get("record_id"),
                "kind": r.get("kind"),
                "title": r.get("title"),
                "year": r.get("year"),
                "genre": r.get("genre"),
                "provider_name": r.get("provider_name"),
                "provider_prefix": r.get("provider_prefix"),
                "stream_url": r.get("stream_url", ""),
                "external_url": r.get("external_url", ""),
                "duration": r.get("ina_duration", ""),
                "detail_url": efg.EFG_BASE + (r.get("detail_path") or ""),
                "thumb": r.get("thumb", ""),
                "description": (r.get("description") or "")[:300],
                "query": r.get("query", ""),
            })
    log(f"wrote {OUT_CSV} ({len(rows)} rows)")


def print_stats(rows: dict[str, dict]) -> None:
    from collections import Counter
    kinds = Counter(r.get("kind", "?") for r in rows.values())
    providers = Counter(r.get("provider_name") or r.get("provider_prefix") or "?" for r in rows.values())
    years = Counter(r.get("year") for r in rows.values() if r.get("year"))
    print("\n== kind ==")
    for k, n in kinds.most_common():
        print(f"  {k:12s} {n}")
    print("\n== top providers ==")
    for p, n in providers.most_common(15):
        print(f"  {n:5d}  {p}")
    print("\n== year buckets ==")
    for decade_start in range(1890, 1950, 10):
        n = sum(c for y, c in years.items() if decade_start <= int(y) < decade_start + 10)
        print(f"  {decade_start}-{decade_start+9}: {n}")
    dl = sum(1 for r in rows.values() if r.get("kind") in ("embedded", "ina", "youtube"))
    print(f"\ndownloadable now: {dl}")


def main() -> None:
    single_instance()
    t0 = time.time()
    records = phase_a()
    rows = phase_b(records)
    write_csv(rows)
    print_stats(rows)
    log(f"total time: {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
