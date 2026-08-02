import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from db import db, queue_stats

with db(write=True) as conn:
    cur = conn.execute(
        "UPDATE queue_items SET downloadable='no', detail='euscreen resolver needed (yt-dlp extractor broken)' "
        "WHERE url LIKE '%euscreen.eu%' AND status='pending' AND downloadable='yes'"
    )
    parked = cur.rowcount
print(f"parked euscreen rows: {parked}")
print(queue_stats())
