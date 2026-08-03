"""Re-render FHO Review stills as full frames: delete cand_{id}.jpg for FHO
candidates so the server's ensure pool refills them via the FHO full-frame
branch (ensure_candidate_still). Rows/crops/strips are kept."""

import sqlite3
from pathlib import Path

CONTACT = Path("output/contact_sheets")
conn = sqlite3.connect("output/shtetlframes.db")

ids = [
    r[0]
    for r in conn.execute(
        "SELECT id FROM candidates WHERE source_url LIKE '%filmhiradokonline.hu%'"
    )
]
print("fho candidates:", len(ids))

deleted = 0
for cid in ids:
    p = CONTACT / f"cand_{cid}.jpg"
    try:
        if p.is_file():
            p.unlink()
            deleted += 1
    except OSError:
        pass
print("stills deleted:", deleted)
