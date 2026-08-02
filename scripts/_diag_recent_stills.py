import json
import sqlite3
import time
from pathlib import Path

CONTACT = Path("output/contact_sheets")
con = sqlite3.connect("output/shtetlframes.db")
con.row_factory = sqlite3.Row

print("id | video_id | created_at | still_file | file_mtime | lag_s | notes_head")
for r in con.execute(
    "SELECT id, video_id, substr(notes,1,40) AS n, created_at FROM candidates "
    "WHERE id >= 5799 ORDER BY id"
):
    cid = r["id"]
    p = CONTACT / f"cand_{cid}.jpg"
    if p.is_file():
        mt = p.stat().st_mtime
        lag = round(mt - r["created_at"], 1)
        f = f"{p.stat().st_size}B"
        mts = time.strftime("%H:%M:%S", time.localtime(mt))
    else:
        lag = None
        f = "MISSING"
        mts = "-"
    cas = time.strftime("%H:%M:%S", time.localtime(r["created_at"]))
    print(f"{cid} | {r['video_id'][:38]:38} | {cas} | {f:>8} | {mts} | {lag} | {r['n']}")
