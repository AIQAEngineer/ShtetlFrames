"""One-off: most recent queue errors (highest ids) and their messages."""
import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

con = sqlite3.connect("output/shtetlframes.db")
rows = con.execute(
    "SELECT id, status, attempts, substr(coalesce(error,''), 1, 110) "
    "FROM queue_items ORDER BY id DESC LIMIT 400"
).fetchall()
err = [r for r in rows if r[1] == "error"]
print(f"of last 400 rows: {len(err)} error")
c = Counter(r[3] for r in err)
for msg, n in c.most_common(8):
    print(f"  x{n}: {msg}")
