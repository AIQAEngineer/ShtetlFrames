import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from config import load_env
load_env()
from db import db

with db() as conn:
    rows = conn.execute(
        """
        SELECT id, best_cue, rank_score, decision,
               substr(notes,1,180) AS notes, substr(title,1,70) AS title
        FROM candidates
        WHERE created_at > ? 
        ORDER BY created_at DESC LIMIT 30
        """,
        ( __import__("time").time() - 86400 * 2,),
    ).fetchall()
    print(f"recent={len(rows)}")
    for r in rows:
        d = dict(r)
        print(f"#{d['id']} {d['rank_score']:.3f} {d['decision'] or 'pending'}")
        print(f"  cue={d['best_cue']}")
        print(f"  title={d['title']}")
        print(f"  notes={d['notes']}")
