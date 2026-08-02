"""Europeana discovery: all videos dated through 1980 across the network.

Uses the Europeana Record API with TYPE:VIDEO + YEAR decade ranges and
cursor-based pagination. Records are deduped by Europeana item id.

State (resumable):
  data/europeana/listing_1980.json       {record_id: record}
  data/europeana/cursor_1980.json        {range_label: nextCursor}
Output:
  output/europeana_discovery_1980.csv

Requires EUROPEANA_API_KEY (or EUROPEANA_KEY) in env/.env.
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
import europeana

STATE_DIR = DATA_DIR / "europeana"
LISTING_JSON = STATE_DIR / "listing_1980.json"
CURSOR_JSON = STATE_DIR / "cursor_1980.json"
OUT_CSV = OUTPUT_DIR / "europeana_discovery_1980.csv"
LOCK_FILE = STATE_DIR / "discovery_1980.lock"

YEAR_RANGES = europeana.THROUGH1980_YEAR_RANGES
WORKERS = 8


def single_instance() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_FILE, "a+b")
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("another europeana discovery instance is running; exiting", flush=True)
        sys.exit(0)
    globals()["_lock_fh"] = fh


def log(msg: str) -> None:
    print(msg, flush=True)


def _load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _save_json(path, obj) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def phase_listing() -> dict[str, dict]:
    records: dict[str, dict] = _load_json(LISTING_JSON, {})
    cursors: dict[str, str] = _load_json(CURSOR_JSON, {})
    log(f"[A] resume: {len(records)} records, cursors={list(cursors.items())}")
    lock = threading.Lock()
    stop = threading.Event()

    def crawl_range(y0: int, y1: int) -> None:
        label = f"{y0}-{y1}"
        cursor = cursors.get(label) or "*"
        total = None
        page = 0
        while not stop.is_set():
            try:
                data = europeana.search("*:*", year_from=y0, year_to=y1, cursor=cursor)
            except Exception as e:
                msg = str(e)[:100]
                log(f"[A] {label} page {page}: {msg}")
                if "429" in msg:
                    time.sleep(20)
                    continue
                break
            if total is None:
                total = europeana.total_results(data)
                log(f"[A] {label}: total≈{total}")
            items, nxt = europeana.parse_items(data)
            with lock:
                for r in items:
                    if r["record_id"]:
                        records[r["record_id"]] = r
            page += 1
            if page % 5 == 0 or not items:
                with lock:
                    cursors[label] = nxt or ""
                    _save_json(LISTING_JSON, records)
                    _save_json(CURSOR_JSON, cursors)
                log(f"[A] {label} p{page} have~{total} union={len(records)}")
            if not items or not nxt or nxt == cursor:
                break
            cursor = nxt
            time.sleep(0.25)
        with lock:
            cursors.pop(label, None)
            _save_json(CURSOR_JSON, cursors)
        log(f"[A] {label} done union={len(records)}")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(crawl_range, y0, y1) for y0, y1 in YEAR_RANGES]
        for f in as_completed(futs):
            f.result()
    _save_json(LISTING_JSON, records)
    log(f"[A] done: {len(records)} unique video records (through 1980)")
    return records


def write_csv(records: dict[str, dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    cols = ["record_id", "title", "year", "provider_name", "edm_is_shown_at",
            "europeana_url", "rights", "type"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in sorted(records.values(), key=lambda x: ((x.get("year") or 9999), x["record_id"])):
            w.writerow({c: r.get(c, "") for c in cols})
    log(f"wrote {OUT_CSV} ({len(records)} rows)")


def print_stats(records: dict[str, dict]) -> None:
    from collections import Counter
    providers = Counter(r.get("provider_name") or "?" for r in records.values())
    years = Counter(r.get("year") for r in records.values() if r.get("year"))
    print("\n== top providers ==")
    for p, n in providers.most_common(15):
        print(f"  {n:6d}  {p}")
    print("\n== year buckets ==")
    for y0, y1 in YEAR_RANGES:
        n = sum(c for y, c in years.items() if y0 <= int(y) <= y1)
        print(f"  {y0}-{y1}: {n}")
    print(f"\ntotal video records through 1980: {len(records)}")


def main() -> None:
    single_instance()
    t0 = time.time()
    records = phase_listing()
    write_csv(records)
    print_stats(records)
    log(f"total time: {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
