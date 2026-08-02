import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from db import db

with db(write=True) as conn:
    cur = conn.execute(
        "DELETE FROM queue_items WHERE source LIKE 'europeana%' AND status='pending'"
    )
    deleted = cur.rowcount
    total = conn.execute("SELECT COUNT(*) AS n FROM queue_items").fetchone()["n"]
print(f"deleted europeana pending rows: {deleted}")
print(f"queue total now: {total}")
