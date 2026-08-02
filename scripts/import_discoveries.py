"""CLI wrapper around src/discovery_import.py.

Run from repo root:  python scripts/import_discoveries.py [--no-efg] [--no-europeana]
Adds src/ to sys.path, then delegates to discovery_import.import_into_queue.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from discovery_import import import_into_queue  # noqa: E402

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
        on_progress=lambda m: print(m, flush=True),
    )
    print(json.dumps(out, indent=2))
