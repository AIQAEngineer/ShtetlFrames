"""Report how many FHO candidate stills have been refilled."""

import sqlite3
from pathlib import Path

ids = [
    r[0]
    for r in sqlite3.connect("output/shtetlframes.db").execute(
        "SELECT id FROM candidates WHERE source_url LIKE '%filmhiradokonline.hu%'"
    )
]
d = Path("output/contact_sheets")
n = sum(1 for i in ids if (d / f"cand_{i}.jpg").is_file())
print(f"{n}/{len(ids)} FHO stills present")
