import sqlite3
import json
import re

conn = sqlite3.connect(r"C:\Users\Avi Schwartz\Documents\hasidic-footage-scan\output\shtetlframes.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print("=== TABLES ===")
for t in tables:
    print(t)

print("\n=== queue_items columns ===")
cur.execute("PRAGMA table_info(queue_items)")
for c in cur.fetchall():
    print(f"  {c['name']} ({c['type']})")

print("\n=== description-like columns ===")
for t in tables:
    cur.execute(f"PRAGMA table_info({t})")
    cols = [r["name"] for r in cur.fetchall()]
    hit = [c for c in cols if any(x in c.lower() for x in ("desc", "meta", "body", "text", "snippet", "detail", "notes"))]
    if hit:
        print(f"  {t}: {hit}")

print("\n=== 20 recent YouTube britishpathe queue_items ===")
cur.execute("""
SELECT id, title, url, status, hub, source_type, created_at
FROM queue_items
WHERE hub LIKE '%britishpathe%' AND (url LIKE '%youtube%' OR url LIKE '%youtu.be%')
ORDER BY id DESC
LIMIT 20
""")
rows = cur.fetchall()
if not rows:
    cur.execute("""
    SELECT id, title, url, status, hub, source_type, created_at
    FROM queue_items
    WHERE hub LIKE '%britishpathe%'
    ORDER BY id DESC
    LIMIT 20
    """)
    rows = cur.fetchall()
for r in rows:
    print(dict(r))

print("\n=== 10 pending Pathé titles ===")
cur.execute("""
SELECT id, title, status, url
FROM queue_items
WHERE hub LIKE '%britishpathe%' AND status = 'pending'
ORDER BY id DESC
LIMIT 10
""")
for r in cur.fetchall():
    print(dict(r))

print("\n=== jobs pathe_discover / pathe_scrape ===")
cur.execute("PRAGMA table_info(jobs)")
job_cols = [r["name"] for r in cur.fetchall()]
print("jobs columns:", job_cols)
cur.execute("SELECT * FROM jobs WHERE job_type LIKE '%pathe%' OR name LIKE '%pathe%' OR id LIKE '%pathe%'")
# try flexible
for q in [
    "SELECT * FROM jobs WHERE job_type IN ('pathe_discover','pathe_scrape')",
    "SELECT * FROM jobs WHERE type IN ('pathe_discover','pathe_scrape')",
    "SELECT * FROM jobs WHERE name IN ('pathe_discover','pathe_scrape')",
]:
    try:
        cur.execute(q)
        jr = cur.fetchall()
        if jr:
            print(f"Query: {q}")
            for r in jr:
                print(dict(r))
    except Exception as e:
        pass

# fallback: all jobs with pathe in any text col
try:
    cur.execute("SELECT * FROM jobs")
    all_jobs = cur.fetchall()
    keys = all_jobs[0].keys() if all_jobs else []
    for r in all_jobs:
        d = dict(r)
        s = json.dumps(d, default=str).lower()
        if 'pathe' in s:
            print("pathe job:", d)
except Exception as e:
    print("jobs error:", e)

conn.close()
