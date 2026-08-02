"""Snapshot: scrape job state + queue status counts + recent error samples."""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

con = sqlite3.connect("output/shtetlframes.db", timeout=30)
con.row_factory = sqlite3.Row

j = con.execute("SELECT * FROM jobs WHERE id='scrape'").fetchone()
if j:
    d = dict(j)
    d["message"] = (d.get("message") or "")[:600]
    print("SCRAPE JOB:", d)

print("\nSTATUS COUNTS:")
for r in con.execute("SELECT status, COUNT(*) c FROM queue_items GROUP BY status"):
    print(" ", dict(r))

print("\nSCANNING/QUEUED LEFTOVERS (should be 0 when idle):")
for r in con.execute(
    "SELECT id, status, substr(title,1,50) t, attempts FROM queue_items WHERE status IN ('scanning','queued','downloading') LIMIT 10"
):
    print(" ", dict(r))

print("\nRECENT ERRORS:")
for r in con.execute(
    "SELECT id, substr(title,1,40) t, attempts, substr(error,1,110) e FROM queue_items WHERE status='error' ORDER BY id DESC LIMIT 12"
):
    print(" ", dict(r))

con.close()
