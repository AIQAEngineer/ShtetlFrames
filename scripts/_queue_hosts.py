"""Host distribution of the upcoming queue (what the scrape will work on next)."""

import sqlite3
import sys
from collections import Counter
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
con = sqlite3.connect("output/shtetlframes.db", timeout=30)

rows = con.execute(
    "SELECT url FROM queue_items WHERE status IN ('queued','pending') ORDER BY id LIMIT 3000"
).fetchall()
hosts = Counter()
for (u,) in rows:
    try:
        hosts[urlparse(u).netloc.lower()] += 1
    except Exception:
        hosts["?"] += 1

print(f"next {len(rows)} queued items by host:")
for h, n in hosts.most_common(15):
    print(f"  {n:>5}  {h}")

tot = con.execute(
    "SELECT COUNT(*) FROM queue_items WHERE status IN ('queued','pending')"
).fetchone()[0]
fn = con.execute(
    "SELECT COUNT(*) FROM queue_items WHERE status IN ('queued','pending') AND url LIKE '%fn.org.pl%'"
).fetchone()[0]
print(f"\ntotal queued+pending: {tot}  ·  fn.org.pl share: {fn} ({100.0*fn/max(tot,1):.0f}%)")
con.close()
