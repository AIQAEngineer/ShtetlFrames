import json
import sqlite3
import time

con = sqlite3.connect("output/shtetlframes.db")
con.row_factory = sqlite3.Row

print("=== queue_items 220640..220660 ===")
for r in con.execute(
    "SELECT id, title, status, substr(detail,1,40) AS d, substr(url,1,60) AS u FROM queue_items WHERE id BETWEEN 220640 AND 220660 ORDER BY id"
):
    print(json.dumps(dict(r), ensure_ascii=False))

print("\n=== candidates 5821..5840 ===")
for r in con.execute(
    "SELECT id, video_id, source_url, substr(notes,1,50) AS n, created_at FROM candidates WHERE id BETWEEN 5821 AND 5840 ORDER BY id"
):
    d = dict(r)
    d["created"] = time.strftime("%H:%M:%S", time.localtime(d.pop("created_at")))
    print(json.dumps(d, ensure_ascii=False))
