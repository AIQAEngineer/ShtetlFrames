import sys

sys.path.insert(0, "src")
from db import db

with db() as conn:
    rows = conn.execute(
        "SELECT status, COUNT(*) c FROM queue_items "
        "WHERE url LIKE '%euscreen.eu%item.html%' OR url LIKE '%iwm.org.uk%/collections/item/%' "
        "GROUP BY status ORDER BY c DESC"
    ).fetchall()
total = 0
for r in rows:
    print(f"{r['status']:>12}: {r['c']}")
    total += r["c"]
print(f"{'total':>12}: {total}")
