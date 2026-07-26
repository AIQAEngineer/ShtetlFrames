import sqlite3
conn = sqlite3.connect(r"C:\Users\Avi Schwartz\Documents\hasidic-footage-scan\output\shtetlframes.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== distinct source values (pathe) ===")
cur.execute("SELECT DISTINCT source FROM queue_items WHERE source LIKE '%pathe%' OR url LIKE '%pathe%' OR hub_url LIKE '%pathe%' OR title LIKE '%Path%' LIMIT 30")
for r in cur.fetchall(): print(r[0])

print("\n=== sample hub_url patterns ===")
cur.execute("SELECT hub_url, COUNT(*) c FROM queue_items WHERE hub_url LIKE '%pathe%' GROUP BY hub_url ORDER BY c DESC LIMIT 10")
for r in cur.fetchall(): print(dict(r))

print("\n=== count by source for youtube pathe ===")
cur.execute("""
SELECT source, status, COUNT(*) FROM queue_items
WHERE (hub_url LIKE '%britishpathe%' OR url LIKE '%youtube%' OR url LIKE '%youtu.be%')
AND (hub_url LIKE '%britishpathe%' OR source LIKE '%pathe%' OR title LIKE '%British Path%')
GROUP BY source, status
""")
for r in cur.fetchall(): print(tuple(r))

print("\n=== 20 recent: hub_url like britishpathe + youtube url ===")
cur.execute("""
SELECT id, title, url, status, source, hub_url, detail
FROM queue_items
WHERE hub_url LIKE '%britishpathe%' AND (url LIKE '%youtube.com%' OR url LIKE '%youtu.be%')
ORDER BY id DESC LIMIT 20
""")
rows = cur.fetchall()
print("count", len(rows))
for r in rows:
    d = dict(r)
    if d.get('detail') and len(str(d['detail']))>80:
        d['detail'] = str(d['detail'])[:80]+'...'
    print(d)

if len(rows)==0:
    print("\n=== fallback: hub_url britishpathe any url ===")
    cur.execute("""
    SELECT id, title, url, status, source, hub_url
    FROM queue_items WHERE hub_url LIKE '%britishpathe%'
    ORDER BY id DESC LIMIT 20
    """)
    for r in cur.fetchall(): print(dict(r))

print("\n=== detail column sample (non-null) for pathe youtube ===")
cur.execute("""
SELECT id, title, LENGTH(detail) as dlen, substr(detail,1,200) as detail_preview
FROM queue_items
WHERE hub_url LIKE '%britishpathe%' AND detail IS NOT NULL AND detail != ''
ORDER BY id DESC LIMIT 5
""")
for r in cur.fetchall(): print(dict(r))

print("\n=== 10 pending pathe ===")
cur.execute("""
SELECT id, title, status, url FROM queue_items
WHERE hub_url LIKE '%britishpathe%' AND status='pending'
ORDER BY id DESC LIMIT 10
""")
for r in cur.fetchall(): print(dict(r))

print("\n=== jobs schema and pathe ===")
cur.execute("PRAGMA table_info(jobs)")
print([r['name'] for r in cur.fetchall()])
cur.execute("SELECT * FROM jobs")
for r in cur.fetchall():
    d = dict(r)
    if any('pathe' in str(v).lower() for v in d.values()):
        print(d)
    elif d.get('job_type') in ('pathe_discover','pathe_scrape') or d.get('type') in ('pathe_discover','pathe_scrape'):
        print(d)

# show all job types if no pathe
cur.execute("SELECT DISTINCT job_type FROM jobs")
try:
    print("job_types:", [r[0] for r in cur.fetchall()])
except:
    cur.execute("SELECT * FROM jobs LIMIT 3")
    for r in cur.fetchall(): print(dict(r))

conn.close()
