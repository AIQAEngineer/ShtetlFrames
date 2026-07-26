import sqlite3
conn = sqlite3.connect(r"C:\Users\Avi Schwartz\Documents\hasidic-footage-scan\output\shtetlframes.db")
cur = conn.cursor()
cur.execute("SELECT status, COUNT(*) FROM queue_items WHERE hub_url='britishpathe.com' AND (title LIKE 'British Path% asset%' OR title LIKE 'Asset %') GROUP BY status")
print("generic asset title counts by status:", cur.fetchall())
cur.execute("SELECT COUNT(*) FROM queue_items WHERE hub_url='britishpathe.com' AND status='pending' AND url LIKE '%/asset/%'")
print("pending with asset url:", cur.fetchone()[0])
conn.close()
