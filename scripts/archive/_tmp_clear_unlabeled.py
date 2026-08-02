"""Delete all candidates except human Keep (accept) and Pass (reject)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import CONTACT_DIR, load_env
from db import db, init_db
from still_store import candidate_crop_path, candidate_still_path


def main() -> int:
    load_env()
    init_db()
    with db(write=True) as conn:
        rows = conn.execute(
            "SELECT id FROM candidates "
            "WHERE decision IS NULL OR decision NOT IN ('accept', 'reject')"
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        conn.execute(
            "DELETE FROM candidates "
            "WHERE decision IS NULL OR decision NOT IN ('accept', 'reject')"
        )
        left = [
            dict(r)
            for r in conn.execute(
                "SELECT decision, COUNT(*) AS n FROM candidates GROUP BY decision"
            ).fetchall()
        ]
    print(f"deleted_rows={len(ids)}", flush=True)
    removed = 0
    for cid in ids:
        for p in (candidate_still_path(cid), candidate_crop_path(cid)):
            try:
                if p.is_file():
                    p.unlink()
                    removed += 1
            except OSError:
                pass
        for p in CONTACT_DIR.glob(f"cand_{cid}*"):
            try:
                if p.is_file():
                    p.unlink()
                    removed += 1
            except OSError:
                pass
    print(f"removed_files={removed}", flush=True)
    print(f"remaining={left}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
