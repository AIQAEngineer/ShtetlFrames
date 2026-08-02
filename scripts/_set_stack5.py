import sqlite3
from pathlib import Path

db = Path("output/shtetlframes.db")
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute(
    "INSERT INTO app_settings(key, value) VALUES('PATHE_STACK_MAX','5') "
    "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
)
con.commit()
row = cur.execute("SELECT value FROM app_settings WHERE key='PATHE_STACK_MAX'").fetchone()
print("PATHE_STACK_MAX =", row[0] if row else None)
con.close()
