"""Diagnose slow FHO still extraction: time one manual extraction."""

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from still_ensure import ensure_candidate_still  # noqa: E402
from still_store import local_still_url  # noqa: E402

conn = sqlite3.connect("output/shtetlframes.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, video_id, start_sec, end_sec, best_time, source_url FROM candidates "
    "WHERE source_url LIKE '%filmhiradokonline.hu%' ORDER BY id DESC LIMIT 400"
).fetchall()

missing = [dict(r) for r in rows if not local_still_url(int(r["id"]))]
print(f"missing among newest 400: {len(missing)}")
if not missing:
    sys.exit(0)

r = missing[0]
print("extracting candidate", r["id"], r["source_url"][:90])
t0 = time.time()
out = ensure_candidate_still(
    int(r["id"]),
    source_url=r["source_url"] or "",
    video_id=r["video_id"] or "",
    start_sec=float(r["start_sec"] or 0),
    end_sec=r["end_sec"],
    best_time=r["best_time"],
    download_video=True,
)
dt = time.time() - t0
print(f"result: {out} in {dt:.1f}s")
if out:
    print("size:", Path(out).stat().st_size)
