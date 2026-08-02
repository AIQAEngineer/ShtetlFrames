import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "src")
con = sqlite3.connect("output/shtetlframes.db")
row = con.execute(
    "SELECT id, url, title FROM queue_items WHERE status='scanning' LIMIT 1"
).fetchone()
print("sample", row)
from britishpathe import resolve_asset

try:
    out = resolve_asset(row[1], force=True)
    print("OK", {k: out.get(k) for k in ("asset_id", "m3u8_url", "title", "cached")})
except Exception as e:
    print("FAIL", type(e).__name__, str(e)[:500])
