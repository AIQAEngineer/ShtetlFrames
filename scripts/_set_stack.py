import sqlite3
import sys
from pathlib import Path

val = sys.argv[1]
db = Path("output/shtetlframes.db")
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute(
    "INSERT INTO app_settings(key, value) VALUES('PATHE_STACK_MAX', ?) "
    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
    (val,),
)
con.commit()
row = cur.execute("SELECT value FROM app_settings WHERE key='PATHE_STACK_MAX'").fetchone()
print("PATHE_STACK_MAX =", row[0] if row else None)
con.close()
