import sqlite3
conn = sqlite3.connect(r"C:\Users\Avi Schwartz\Documents\hasidic-footage-scan\output\shtetlframes.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT title FROM queue_items WHERE hub_url='britishpathe.com' AND title LIKE '%asset%' LIMIT 15")
print("=== titles with asset ===")
for r in cur.fetchall(): print(r[0])
cur.execute("SELECT id, title, url, detail FROM queue_items WHERE source='British Pathé' AND status='pending' ORDER BY id DESC LIMIT 10")
print("\n=== pending source=British Pathé ===")
for r in cur.fetchall(): print(dict(r))
cur.execute("SELECT id, status, phase, message, error FROM jobs WHERE id='pathe_discover' OR id='pathe_scrape' OR id='discover'")
print("\n=== jobs ===")
for r in cur.fetchall(): print(dict(r))
conn.close()
