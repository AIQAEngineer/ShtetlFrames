"""Diagnose Kept filter hiding human accepts without openai:keep."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from db import connect, init_db
from openai_verify import (
    notes_openai_approved,
    notes_openai_dropped,
    notes_openai_uncertain,
    openai_verify_enabled,
)

init_db()
c = connect().cursor()
accepts = [
    dict(r)
    for r in c.execute(
        "SELECT id, decision, notes FROM candidates WHERE decision='accept' ORDER BY id"
    ).fetchall()
]
print("total accept", len(accepts))
print("openai_verify_enabled", openai_verify_enabled())
ok = drop = unc = other = 0
missing = []
for r in accepts:
    n = r.get("notes") or ""
    if notes_openai_approved(n):
        ok += 1
    elif notes_openai_dropped(n):
        drop += 1
        missing.append((r["id"], "drop", n[:140]))
    elif notes_openai_uncertain(n):
        unc += 1
        missing.append((r["id"], "uncertain", n[:140]))
    else:
        other += 1
        missing.append((r["id"], "no_tag", n[:140]))
print(f"approved={ok} dropped={drop} uncertain={unc} no_tag={other}")
print("hidden_from_kept_filter", drop + unc + other)
for m in missing[:40]:
    print(m)
