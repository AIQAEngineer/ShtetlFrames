"""Full EFG discovery scrape.

Phase A: scrape search listings for a curated multilingual query set
(pre-war Jewish Europe focus), dedupe by record id, checkpoint to
data/efg/listing.json.

Phase B: resolve every unique record (detail page -> stream URL or
external provider link), JSONL checkpoint to data/efg/resolve.jsonl.

Final: output/efg_discovery.csv + provider/kind stats.

Resumable: re-run after interruption; completed phases are skipped.
"""

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
LISTING_JSON = STATE_DIR / "listing.json"
RESOLVE_JSONL = STATE_DIR / "resolve.jsonl"
OUT_CSV = OUTPUT_DIR / "efg_discovery.csv"
LOCK_FILE = STATE_DIR / "discovery.lock"


def single_instance() -> None:
    """Exit immediately if another discovery process holds the lock.

    The shell launcher occasionally spawns the same command twice; only the
    first process should proceed.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_FILE, "a+b")
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("another discovery instance is running; exiting", flush=True)
        sys.exit(0)
    globals()["_lock_fh"] = fh

LISTING_WORKERS = 4
RESOLVE_WORKERS = 12
MAX_PAGES_PER_QUERY = 40  # 400 records/query ceiling

QUERIES = [
    # Jewish terms — EN / FR / DE / PL
    "jewish", "jews", "juif", "juifs", "jüdisch", "juden", "żydzi",
    "hebrew", "hébreu", "yiddish", "shtetl", "synagogue", "synagoge", "rabbi",
    "zionist", "zionism", "palestine", "jerusalem", "jérusalem", "tel aviv",
    "kosher", "passover", "sabbath", "yom kippur",
    # Pre-war European Jewish geography
    "warsaw", "varsovie", "warschau", "warszawa",
    "krakow", "cracow", "cracovie", "krakau", "lodz",
    "vilna", "vilnius", "wilna", "lwow", "lviv", "lemberg",
    "bialystok", "galicia", "galicie", "minsk", "odessa", "kiev",
    "budapest", "prague", "prag", "vienna", "wien", "berlin",
    "amsterdam", "poland", "pologne", "polen", "romania", "roumanie",
]

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def phase_a() -> dict[str, dict]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if LISTING_JSON.exists():
        data = json.loads(LISTING_JSON.read_text(encoding="utf-8"))
        log(f"[A] resume: {len(data)} records already listed")
        return data

    records: dict[str, dict] = {}
    lock = threading.Lock()

    def scrape_query(query: str) -> None:
        page = 0
        last = 0
        while page <= min(last, MAX_PAGES_PER_QUERY - 1):
            url = efg.search_url(query, page)
            try:
                html = efg._scrapfly_html(url)
                recs, last = efg.parse_search_page(html, query)
            except Exception as e:
                log(f"[A] {query!r} p{page}: {str(e)[:120]}")
                break
            with lock:
                for r in recs:
                    rid = r["record_id"]
                    if rid in records:
                        if query not in records[rid].setdefault("queries", [records[rid]["query"]]):
                            records[rid].setdefault("queries", []).append(query)
                    else:
                        r["queries"] = [query]
                        records[rid] = r
            if not recs:
                break
            page += 1
        with lock:
            total = len(records)
        log(f"[A] {query!r}: {page} page(s), union total {total}")

    with ThreadPoolExecutor(max_workers=LISTING_WORKERS) as pool:
        futs = {pool.submit(scrape_query, q): q for q in QUERIES}
        for f in as_completed(futs):
            f.result()

    LISTING_JSON.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    log(f"[A] done: {len(records)} unique records -> {LISTING_JSON}")
    return records


def phase_b(records: dict[str, dict]) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if RESOLVE_JSONL.exists():
        for line in RESOLVE_JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                done[row["record_id"]] = row
            except Exception:
                continue
        log(f"[B] resume: {len(done)} already resolved")

    todo = [r for rid, r in records.items() if rid not in done]
    log(f"[B] resolving {len(todo)} records with {RESOLVE_WORKERS} workers")

    out_lock = threading.Lock()
    fh = RESOLVE_JSONL.open("a", encoding="utf-8")
    count = [0]

    def work(rec: dict) -> None:
        res = efg.resolve_record(rec)
        res.pop("queries", None)
        with out_lock:
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            fh.flush()
            count[0] += 1
            done[res["record_id"]] = res
            n = count[0]
        if n % 25 == 0 or n == len(todo):
            log(f"[B] {n}/{len(todo)} resolved (total {len(done)})")

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
                "detail_url": efg.EFG_BASE + r.get("detail_path", ""),
                "thumb": r.get("thumb", ""),
                "description": r.get("description", "")[:300],
                "query": r.get("query", ""),
            })
    print(f"wrote {OUT_CSV} ({len(rows)} rows)")


def print_stats(rows: dict[str, dict]) -> None:
    kinds: dict[str, int] = {}
    providers: dict[str, int] = {}
    prewar_downloadable = 0
    for r in rows.values():
        kinds[r.get("kind", "?")] = kinds.get(r.get("kind", "?"), 0) + 1
        p = r.get("provider_name") or r.get("provider_prefix") or "?"
        providers[p] = providers.get(p, 0) + 1
        if r.get("kind") in ("embedded", "ina") and (r.get("year") or 9999) <= 1939:
            prewar_downloadable += 1
    print("\n== kind breakdown ==")
    for k, n in sorted(kinds.items(), key=lambda x: -x[1]):
        print(f"  {k:12s} {n}")
    print("\n== top providers ==")
    for p, n in sorted(providers.items(), key=lambda x: -x[1])[:15]:
        print(f"  {n:5d}  {p}")
    print(f"\npre-war (<=1939) directly downloadable: {prewar_downloadable}")


def main() -> None:
    single_instance()
    t0 = time.time()
    records = phase_a()
    rows = phase_b(records)
    write_csv(rows)
    print_stats(rows)
    print(f"\ntotal time: {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
