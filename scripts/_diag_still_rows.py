import json
import sqlite3

con = sqlite3.connect("output/shtetlframes.db")
con.row_factory = sqlite3.Row

print("=== candidates 5798..5822 ===")
for r in con.execute(
    "SELECT id, video_id, start_sec, end_sec, substr(notes,1,60) AS n, created_at "
    "FROM candidates WHERE id BETWEEN 5798 AND 5822 ORDER BY id"
):
    print(json.dumps(dict(r)))

print("\n=== queue items for affected efg video_ids ===")
vids = [
    "efg_monsieur",
    "efg_captain_kate",
    "efg_the_hero_track_walker",
    "efg_dyrekobt_aere",
    "efg_the_railway_mail_clerk",
]
q = ",".join("?" * len(vids))
try:
    rows = con.execute(
        f"SELECT * FROM queue_items WHERE title LIKE '%monsieur%' OR url LIKE '%vDI3mxen3JM%' OR url LIKE '%NPAt_655pUw%' OR url LIKE '%MraLW_0AzDA%' OR url LIKE '%knL98l7wg-Q%' OR url LIKE '%qrb4IXHihrk%'",
    ).fetchall()
    for r in rows:
        d = dict(r)
        for k in d:
            if isinstance(d[k], str) and len(d[k]) > 200:
                d[k] = d[k][:200] + "…"
        print(json.dumps(d, default=str))
except Exception as e:
    print("queue query err:", e)
