"""Delete FHO stills that are pod crop collages ("slices") rather than full
frames, so the ensure pool refills them with full frames.

Collage detection: very wide aspect ratio (crops laid side by side) or a
suspiciously tiny JPEG (mostly-black collage compresses to ~1-3 KB while a
real 384x288 frame is ~20-35 KB).
"""

import sqlite3
from pathlib import Path

CONTACT = Path("output/contact_sheets")

try:
    from PIL import Image

    HAVE_PIL = True
except Exception:
    HAVE_PIL = False
    print("PIL unavailable — size-only detection")

ids = [
    r[0]
    for r in sqlite3.connect("output/shtetlframes.db").execute(
        "SELECT id FROM candidates WHERE source_url LIKE '%filmhiradokonline.hu%'"
    )
]

deleted = 0
kept = 0
for cid in ids:
    p = CONTACT / f"cand_{cid}.jpg"
    if not p.is_file():
        continue
    is_slice = p.stat().st_size < 6000
    if not is_slice and HAVE_PIL:
        try:
            with Image.open(p) as im:
                w, h = im.size
            if h > 0 and (w / h) > 1.9:
                is_slice = True
        except Exception:
            pass
    if is_slice:
        try:
            p.unlink()
            deleted += 1
        except OSError:
            pass
    else:
        kept += 1

print(f"slice stills deleted: {deleted}, full frames kept: {kept}")
