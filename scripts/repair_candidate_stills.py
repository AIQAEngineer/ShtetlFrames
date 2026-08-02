"""Re-extract missing Review stills for candidate ids (one-shot repair).

Reuses still_ensure.ensure_candidate_still: local video files are reused when
present (data/videos/<video_id>.*), otherwise the source is downloaded once per
video and the mid-segment frame is extracted. Safe alongside the serve process —
it skips candidates whose still already exists.

Usage:
    .\.venv\Scripts\python.exe scripts\repair_candidate_stills.py 5807 5809 5811
    .\.venv\Scripts\python.exe scripts\repair_candidate_stills.py --all-missing
    .\.venv\Scripts\python.exe scripts\repair_candidate_stills.py --missing-keeps
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from still_ensure import ensure_candidate_still  # noqa: E402
from still_store import local_still_url  # noqa: E402

DB = ROOT / "output" / "shtetlframes.db"


def rows_for_ids(ids: list[int]) -> list[dict]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    q = ",".join("?" * len(ids))
    return [
        dict(r)
        for r in con.execute(
            f"SELECT id, video_id, source_url, image_url, start_sec, end_sec, notes "
            f"FROM candidates WHERE id IN ({q}) ORDER BY id",
            ids,
        )
    ]


def missing_ids(*, keeps_only: bool, limit: int = 200) -> list[int]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    out: list[int] = []
    for r in con.execute(
        "SELECT id, notes FROM candidates ORDER BY id DESC LIMIT ?", (limit * 4,)
    ):
        cid = int(r["id"])
        if local_still_url(cid):
            continue
        if keeps_only and "openai:keep" not in (r["notes"] or ""):
            continue
        out.append(cid)
        if len(out) >= limit:
            break
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", type=int)
    ap.add_argument("--all-missing", action="store_true")
    ap.add_argument("--missing-keeps", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    ids = list(args.ids)
    if args.all_missing:
        ids = missing_ids(keeps_only=False, limit=args.limit)
    elif args.missing_keeps:
        ids = missing_ids(keeps_only=True, limit=args.limit)
    if not ids:
        print("nothing to repair")
        return 0

    print(f"repairing {len(ids)} candidate still(s): {ids}")
    ok_n, skip_n, fail_n = 0, 0, 0
    t0 = time.time()
    for cid in ids:
        if local_still_url(cid):
            print(f"#{cid}: already has still — skip")
            skip_n += 1
            continue
        rows = rows_for_ids([cid])
        if not rows:
            print(f"#{cid}: not in DB — skip")
            skip_n += 1
            continue
        r = rows[0]
        t1 = time.time()
        try:
            saved = ensure_candidate_still(
                cid,
                source_url=(r.get("source_url") or "").strip(),
                video_id=(r.get("video_id") or "").strip(),
                start_sec=float(r.get("start_sec") or 0.0),
                end_sec=r.get("end_sec"),
                image_url=r.get("image_url"),
                download_video=True,
            )
        except Exception as e:
            print(f"#{cid}: ERROR {e}")
            saved = None
        if saved:
            ok_n += 1
            print(f"#{cid}: saved {saved.name} ({time.time() - t1:.1f}s)")
        else:
            fail_n += 1
            print(f"#{cid}: FAILED ({time.time() - t1:.1f}s)")
    print(f"done in {time.time() - t0:.1f}s — saved={ok_n} skipped={skip_n} failed={fail_n}")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
