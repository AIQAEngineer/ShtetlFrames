"""Re-resolve records misclassified as linked_out (YouTube embeds) or error.

After the parser learned video data-setup YouTube sources, records that
previously surfaced the videojs fallback link (or failed transiently) get a
second pass. Rewrites data/efg/resolve.jsonl and regenerates the CSV/stats.
"""

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import DATA_DIR
import efg
import efg_discovery as disc

STATE_DIR = DATA_DIR / "efg"
WORKERS = 12

RERESOLVE_KINDS = {"linked_out", "error"}


def main() -> None:
    disc.single_instance()
    listing = json.loads(disc.LISTING_JSON.read_text(encoding="utf-8"))
    rows: dict[str, dict] = {}
    for line in disc.RESOLVE_JSONL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["record_id"]] = r

    todo = []
    for rid, row in rows.items():
        if row.get("kind") not in RERESOLVE_KINDS:
            continue
        # linked_out records with a genuine provider link keep it unless the
        # new parse finds an actual player.
        src = listing.get(rid) or {k: row.get(k) for k in (
            "record_id", "provider_prefix", "detail_path", "title", "year",
            "genre", "provider_name", "thumb", "description", "query")}
        todo.append(src)
    print(f"re-resolving {len(todo)} records", flush=True)

    lock = threading.Lock()
    done_n = [0]
    upgraded = {"youtube": 0, "embedded": 0, "ina": 0}

    def work(rec: dict) -> None:
        res = efg.resolve_record(rec)
        res.pop("queries", None)
        with lock:
            rows[res["record_id"]] = res
            done_n[0] += 1
            if res.get("kind") in upgraded:
                upgraded[res["kind"]] += 1
            n = done_n[0]
        if n % 50 == 0 or n == len(todo):
            print(f"  {n}/{len(todo)} (youtube +{upgraded['youtube']}, "
                  f"embedded +{upgraded['embedded']}, ina +{upgraded['ina']})", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(work, r) for r in todo]
        for f in as_completed(futs):
            f.result()

    tmp = disc.RESOLVE_JSONL.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows.values():
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(disc.RESOLVE_JSONL)
    print("checkpoint rewritten", flush=True)

    disc.write_csv(rows)
    disc.print_stats(rows)


if __name__ == "__main__":
    main()
