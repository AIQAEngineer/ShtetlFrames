import sqlite3
import sys
from pathlib import Path

db_path = Path(__file__).resolve().parents[1] / "output" / "shtetlframes.db"
conn = sqlite3.connect(str(db_path), timeout=20)
conn.row_factory = sqlite3.Row
PATHE = "url LIKE '%britishpathe.com%'"

print("=== Pathé queue status counts ===")
for r in conn.execute(
    f"SELECT status, COUNT(*) n FROM queue_items WHERE {PATHE} GROUP BY status ORDER BY n DESC"
):
    print(f"  {r['status']:<12} {r['n']}")

print("\n=== In-flight rows (queued/scanning/downloading/uploading) ===")
inflight = conn.execute(
    f"SELECT id, status, substr(coalesce(title,''),1,70) t, substr(coalesce(detail,''),1,60) d "
    f"FROM queue_items WHERE {PATHE} AND status IN ('queued','scanning','downloading','uploading') ORDER BY id"
).fetchall()
for r in inflight:
    print(f"  #{r['id']:<7} {r['status']:<12} {r['t']:<70} {r['d']}")

print("\n=== Error rows ===")
errs = conn.execute(
    f"SELECT id, substr(coalesce(title,''),1,70) t, substr(coalesce(error,''),1,50) e "
    f"FROM queue_items WHERE {PATHE} AND status='error' ORDER BY id"
).fetchall()
for r in errs:
    print(f"  #{r['id']:<7} {r['t']:<70} {r['e']}")

if "--apply" not in sys.argv:
    print("\n(dry run — pass --apply to reset scanning+error rows to pending)")
    sys.exit(0)

cur = conn.execute(
    f"UPDATE queue_items SET status='pending', error='', detail='manual_reset_wedged' "
    f"WHERE {PATHE} AND status IN ('scanning','downloading','uploading')"
)
n_scan = cur.rowcount or 0
cur = conn.execute(
    f"UPDATE queue_items SET status='pending', error='', detail='manual_reset_error' "
    f"WHERE {PATHE} AND status='error'"
)
n_err = cur.rowcount or 0
conn.commit()
print(f"\nreset in-flight -> pending: {n_scan}")
print(f"reset error    -> pending: {n_err}")
conn.close()
