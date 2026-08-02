import sqlite3
import time
from pathlib import Path

import requests

DB = Path("output/shtetlframes.db")
pods = [
    "mis60b95ted4b2",
    "b0ybwkjmt25g5x",
    "q7akco35i6idht",
    "00fzi44ynwiho4",
    "wravpkqt5oapmz",
    "opdzcrsd0hujvv",
    "zknbprp8mvwhlm",
    "8dwxykrtty9myk",
]

con = sqlite3.connect(DB)
print("status:", dict(con.execute("select status, count(*) from queue_items group by status")))
print("settings:", con.execute(
    "select key, value from app_settings where key in ('PATHE_STACK_MAX','RUNPOD_MAX_INFLIGHT')"
).fetchall())
print("scanning ids:", [r[0] for r in con.execute(
    "select id from queue_items where status='scanning' order by id limit 30"
)])
con.close()

print("\npod health/inflight:")
for pid in pods:
    try:
        h = requests.get(f"https://{pid}-8000.proxy.runpod.net/health", timeout=18).json()
        p = h.get("progress") or {}
        print(
            f"  {pid}: inflight={h.get('inflight')} phase={p.get('phase')} "
            f"q={p.get('queue_id')} pct={p.get('pct')} msg={(p.get('msg') or '')[:50]!r}"
        )
    except Exception as e:
        print(f"  {pid}: ERR {type(e).__name__}: {e}")
