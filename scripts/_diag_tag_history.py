import sqlite3
import time

con = sqlite3.connect("output/shtetlframes.db")
con.row_factory = sqlite3.Row

total = con.execute("SELECT COUNT(*) c FROM candidates").fetchone()["c"]
nsb = con.execute(
    "SELECT COUNT(*) c FROM candidates WHERE notes LIKE '%no_still_bytes%'"
).fetchone()["c"]
shm = con.execute(
    "SELECT COUNT(*) c FROM candidates WHERE notes LIKE '%still_hydrate_miss%'"
).fetchone()["c"]
sse = con.execute(
    "SELECT COUNT(*) c FROM candidates WHERE notes LIKE '%still_save_err%'"
).fetchone()["c"]
print(f"total={total} no_still_bytes={nsb} still_hydrate_miss={shm} still_save_err={sse}")

print("\nfirst/last no_still_bytes:")
for r in con.execute(
    "SELECT id, created_at FROM candidates WHERE notes LIKE '%no_still_bytes%' ORDER BY id ASC LIMIT 3"
):
    print(" ", r["id"], time.strftime("%m-%d %H:%M:%S", time.localtime(r["created_at"])))

print("\nhourly breakdown (last 24h):")
for r in con.execute(
    """
    SELECT strftime('%H', created_at, 'unixepoch') AS hr,
           COUNT(*) AS n,
           SUM(notes LIKE '%no_still_bytes%') AS nsb
    FROM candidates
    WHERE created_at > ?
    GROUP BY hr ORDER BY hr
    """,
    (time.time() - 86400,),
):
    print(f"  hour {r['hr']}: total={r['n']} no_still_bytes={r['nsb']}")

print("\nany still_hydrate_miss rows (sample):")
for r in con.execute(
    "SELECT id, substr(notes,1,90) n FROM candidates WHERE notes LIKE '%still_hydrate_miss%' LIMIT 5"
):
    print(" ", r["id"], r["n"])
