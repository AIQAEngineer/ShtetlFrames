"""One-off: did any candidates land since the probe install (~15:00 UTC)?"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

con = sqlite3.connect("output/shtetlframes.db")
row = con.execute(
    "SELECT COUNT(*), MAX(created_at) FROM candidates WHERE created_at > '2026-08-02 14:55'"
).fetchone()
print(f"candidates since probe install: {row[0]} (latest: {row[1]})")
for status, n in con.execute(
    "SELECT status, COUNT(*) FROM queue_items GROUP BY status ORDER BY 2 DESC"
):
    print(f"  queue {status}: {n}")
