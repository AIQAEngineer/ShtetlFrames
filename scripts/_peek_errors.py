"""Find queue rows touched in the last 15 minutes and their statuses."""

import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
con = sqlite3.connect("output/shtetlframes.db", timeout=30)
con.row_factory = sqlite3.Row

cols = [r[1] for r in con.execute("PRAGMA table_info(queue_items)")]
print("columns:", cols)

tcol = "updated_at" if "updated_at" in cols else ("updated" if "updated" in cols else None)
if tcol:
    cutoff = time.time() - 900
    q = (
        f"SELECT id, status, attempts, substr(COALESCE(error,''),1,120) e, "
        f"substr(COALESCE(detail,''),1,80) d FROM queue_items WHERE {tcol} > ? "
        f"ORDER BY {tcol} DESC LIMIT 15"
    )
    for r in con.execute(q, (cutoff,)):
        print(dict(r))
else:
    print("no timestamp column — statuses by id range 220500-220700:")
    for r in con.execute(
        "SELECT id, status, attempts, substr(COALESCE(error,''),1,110) e "
        "FROM queue_items WHERE id BETWEEN 220500 AND 220700 AND status != 'queued' LIMIT 15"
    ):
        print(dict(r))
con.close()
