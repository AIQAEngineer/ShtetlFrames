"""Park fn.org.pl queue items while the host is down (2026-08-02 outage).

Sets status='error' + attempts=99 so take_pending skips them. Requeue later with:
  UPDATE queue_items SET status='pending', attempts=0, error=''
  WHERE error LIKE 'parked: fn.org.pl host down%';
"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
con = sqlite3.connect("output/shtetlframes.db", timeout=30)
cur = con.execute(
    "UPDATE queue_items SET status='error', attempts=99, "
    "error='parked: fn.org.pl host down (2026-08-02)' "
    "WHERE status IN ('queued','pending','scanning') AND url LIKE '%fn.org.pl%'"
)
con.commit()
print(f"parked {cur.rowcount} fn.org.pl items")
left = con.execute(
    "SELECT COUNT(*) FROM queue_items WHERE status IN ('queued','pending') AND url LIKE '%fn.org.pl%'"
).fetchone()[0]
print(f"fn.org.pl still claimable: {left}")
con.close()
