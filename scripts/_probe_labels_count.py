"""Count confirmed Keep/Pass review labels and still availability."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from db import db, init_db  # noqa: E402
from clip_ft import _still_for_candidate  # noqa: E402


def main() -> None:
    init_db()
    with db() as conn:
        rows = conn.execute(
            "SELECT decision, COUNT(*) AS n FROM candidates GROUP BY decision"
        ).fetchall()
        by_decision = {str(r["decision"]): int(r["n"]) for r in rows}
        labeled = conn.execute(
            "SELECT id, decision FROM candidates WHERE decision IN ('accept','reject') ORDER BY id"
        ).fetchall()

    n_keep = sum(1 for r in labeled if r["decision"] == "accept")
    n_pass = sum(1 for r in labeled if r["decision"] == "reject")

    keep_with_still = []
    pass_with_still = []
    missing = []
    for r in labeled:
        cid = int(r["id"])
        p = _still_for_candidate(cid)
        if p is None:
            missing.append(cid)
        elif r["decision"] == "accept":
            keep_with_still.append(cid)
        else:
            pass_with_still.append(cid)

    out = {
        "by_decision": by_decision,
        "n_keep_accept": n_keep,
        "n_pass_reject": n_pass,
        "keep_with_still": len(keep_with_still),
        "pass_with_still": len(pass_with_still),
        "missing_still_ids": missing[:50],
        "n_missing_still": len(missing),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
