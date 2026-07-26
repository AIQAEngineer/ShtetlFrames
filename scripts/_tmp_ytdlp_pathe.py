import sqlite3, re, json, sys
try:
    import yt_dlp
except ImportError:
    print("NO_YT_DLP")
    sys.exit(1)

conn = sqlite3.connect(r"C:\Users\Avi Schwartz\Documents\hasidic-footage-scan\output\shtetlframes.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# pick 3 samples: British Pathé or Archive Highlights
cur.execute("""
SELECT id, title, url FROM queue_items
WHERE hub_url LIKE '%britishpathe%'
  AND (url LIKE '%youtube.com%' OR url LIKE '%youtu.be%')
  AND (title LIKE '%British Path%' OR title LIKE '%Archive%')
ORDER BY id DESC
LIMIT 30
""")
candidates = cur.fetchall()
picked = []
for r in candidates:
    t = r['title']
    if 'British Path' in t or 'Archive Highlights' in t or 'Archive footage' in t:
        picked.append(r)
    if len(picked) >= 3:
        break
if len(picked) < 3:
    picked = candidates[:3]

print("=== SAMPLES ===")
for r in picked:
    print(dict(r))

patterns = [
    (r'britishpathe\.com', 'britishpathe.com'),
    (r'/asset/\d+', '/asset/NNN'),
    (r'film\s*#?\s*\d+', 'film number'),
    (r'[A-Z]{2}\d{4,}', 'issue code'),
    (r'www\.youtube\.com', 'youtube'),
]

def analyze(text, label):
    print(f"\n--- {label} ---")
    if not text:
        print("(empty)")
        return
    print(text[:2500])
    if len(text) > 2500:
        print(f"... [{len(text)} chars total]")
    for pat, name in patterns:
        m = re.findall(pat, text, re.I)
        if m:
            print(f"  MATCH {name}: {m[:10]}")

ydl_opts = {'quiet': True, 'skip_download': True, 'no_warnings': True}
for r in picked:
    url = r['url']
    print(f"\n========== yt-dlp: {r['id']} ==========")
    analyze(r['title'], 'DB title')
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        desc = info.get('description') or ''
        analyze(desc, 'YouTube description')
        # also check webpage_url, channel, tags
        tags = info.get('tags') or []
        if tags:
            print('  tags sample:', tags[:15])
        for k in ('webpage_url', 'original_url', 'alt_title'):
            if info.get(k):
                print(f"  {k}: {info[k]}")
    except Exception as e:
        print('ERROR:', e)

# pending title patterns
print("\n=== PENDING British Pathé source (hub britishpathe.com) title patterns ===")
cur.execute("""
SELECT title FROM queue_items
WHERE hub_url = 'britishpathe.com' AND status='pending'
ORDER BY id DESC LIMIT 200
""")
titles = [r[0] for r in cur.fetchall()]
asset_only = sum(1 for t in titles if re.match(r'^British Path[eé] asset \d+$', t, re.I))
print(f"sample n={len(titles)}, asset-only pattern count={asset_only}")
for t in titles[:10]:
    print(' ', t)

print("\n=== PENDING YouTube crawl pathe hub (10 titles) ===")
cur.execute("""
SELECT id, title FROM queue_items
WHERE hub_url LIKE '%youtube.com/@britishpathe%' AND status='pending'
ORDER BY id DESC LIMIT 10
""")
for r in cur.fetchall():
    print(dict(r))

# detail field stats for youtube pathe
cur.execute("""
SELECT 
  SUM(CASE WHEN detail IS NULL OR detail='' THEN 1 ELSE 0 END) as empty,
  SUM(CASE WHEN detail IS NOT NULL AND detail != '' THEN 1 ELSE 0 END) as nonempty,
  COUNT(*) as total
FROM queue_items
WHERE hub_url LIKE '%youtube.com/@britishpathe%'
""")
print("\n=== YouTube @britishpathe detail column ===", dict(zip(['empty','nonempty','total'], cur.fetchone())))

cur.execute("PRAGMA table_info(candidates)")
print("candidates columns:", [r[1] for r in cur.fetchall()])

conn.close()
