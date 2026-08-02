import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from db import db

with db() as conn:
    rows = conn.execute(
        "SELECT status, downloadable, COUNT(*) AS n FROM queue_items WHERE url LIKE '%euscreen.eu%' GROUP BY status, downloadable"
    ).fetchall()
    for r in rows:
        print(dict(r))
    errs = conn.execute(
        "SELECT COUNT(*) AS n FROM queue_items WHERE url LIKE '%euscreen.eu%' AND status='error'"
    ).fetchone()
    print("euscreen errors:", errs["n"])
    sample = conn.execute(
        "SELECT status, error FROM queue_items WHERE url LIKE '%euscreen.eu%' AND status='error' LIMIT 3"
    ).fetchall()
    for s in sample:
        print(" ", s["status"], (s["error"] or "")[:160])
