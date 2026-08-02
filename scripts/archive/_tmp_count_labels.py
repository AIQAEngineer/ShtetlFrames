import sys
from pathlib import Path

sys.path.insert(0, "src")
from config import CONTACT_DIR
from db import db, init_db

init_db()
with db() as c:
    print(
        "accept",
        c.execute("select count(1) from candidates where decision='accept'").fetchone()[0],
    )
    print(
        "reject",
        c.execute("select count(1) from candidates where decision='reject'").fetchone()[0],
    )
for name in ("cand_1825.jpg", "cand_1806.jpg", "cand_1831.jpg"):
    p = CONTACT_DIR / name
    print(name, p.is_file(), p.stat().st_size if p.is_file() else 0)
