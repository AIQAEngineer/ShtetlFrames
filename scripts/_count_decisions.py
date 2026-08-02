import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from config import load_env
from db import db, init_db

load_env()
init_db()
with db() as c:
    rows = [dict(r) for r in c.execute("SELECT decision, COUNT(*) n FROM candidates GROUP BY decision").fetchall()]
    print("candidates", rows)
    acc = [
        dict(r)
        for r in c.execute(
            "SELECT id, peak_score, best_cue, notes FROM candidates WHERE decision='accept' ORDER BY id"
        ).fetchall()
    ]
    print("accept_n", len(acc))
    for r in acc:
        print(r["id"], r["peak_score"], (r["best_cue"] or "")[:50])
