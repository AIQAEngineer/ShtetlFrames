import sqlite3

con = sqlite3.connect("output/shtetlframes.db", timeout=30)
con.execute("UPDATE jobs SET status='running' WHERE id='scrape'")
con.commit()
print("status:", con.execute("SELECT status FROM jobs WHERE id='scrape'").fetchone())
con.close()
