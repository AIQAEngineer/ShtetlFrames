import os
import sqlite3

from config import DB_PATH, DATA_DIR

print("db:", DB_PATH, os.path.exists(DB_PATH))
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

terms = ["jew", "jewish", "hebrew", "rabbi"]

rows = conn.execute(
    """
    SELECT id, url, title, status, created_at
    FROM queue_items
    WHERE url LIKE '%britishpathe.com%' AND status='done'
    """
).fetchall()
print("pathe done rows:", len(rows))


def match(text):
    s = (text or "").lower()
    return [x for x in terms if x in s]


hits = [r for r in rows if match(r["title"]) or match(r["url"])]
print("hits:", len(hits))
for r in hits[:300]:
    m = sorted(set(match(r["title"]) + match(r["url"])))
    print(f"- [{','.join(m)}] {r['title']} — {r['url']}")

placeholder = conn.execute(
    "SELECT COUNT(*) AS n FROM queue_items "
    "WHERE url LIKE '%britishpathe.com%' AND status='done' "
    "AND (title LIKE 'Asset %' OR title LIKE 'British Path%asset%' OR title='' OR title IS NULL)"
).fetchone()["n"]
print("placeholder done titles:", placeholder)

# inspect local resolve cache size (only m3u8/title/thumb — not full page HTML)
cache = DATA_DIR / "pathe_resolve_cache.json"
print("resolve cache exists:", cache.is_file(), cache.stat().st_size if cache.is_file() else 0)
