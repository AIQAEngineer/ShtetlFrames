"""Backfill missing Review stills by grabbing a frame at each candidate timestamp.

Downloads each source video once (YouTube / Pathé / direct), extracts JPEGs with
ffmpeg (OpenCV fallback), saves to output/contact_sheets/cand_{id}.jpg, then
deletes the local video.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env  # noqa: E402
from db import init_db  # noqa: E402
from still_ensure import backfill_missing_stills  # noqa: E402


def main() -> int:
    load_env()
    init_db()
    result = backfill_missing_stills(limit=20000)
    if result.get("missing", 0) == 0:
        print("Nothing to backfill — all candidates with source URLs already have local stills.")
        return 0
    print(
        f"\nDone. saved={result.get('saved')} failed={result.get('failed')} "
        f"still_missing={result.get('still_missing')}"
    )
    return 0 if int(result.get("saved") or 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
