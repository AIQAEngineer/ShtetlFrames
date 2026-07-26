#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / "output" / "candidate_rescore_report.json").read_text(encoding="utf-8"))
rows = report["rows"]
accepts = []
seen = set()
for r in rows:
    if r.get("decision") != "accept":
        continue
    if r["id"] in seen:
        continue
    seen.add(r["id"])
    accepts.append(r)

lines = []
lines.append("")
lines.append("=" * 78)
lines.append("F) HISTORICAL SNAPSHOT from candidate_rescore_report.json")
lines.append("=" * 78)
lines.append(
    "Current shtetlframes.db has 0 accepts / 0 Munkacs rows (DB appears reset). "
    "This section recovers Review labels from the earlier rescore report (n_total=1375)."
)
s = report.get("summary") or {}
lines.append(
    f"Report summary decisions among scored: by_decision_pass={s.get('by_decision_pass')}"
)
lines.append(f"Report row decision counts: {dict(Counter((r.get('decision') or '') for r in rows))}")
lines.append(f"Report row openai counts: {dict(Counter((r.get('openai') or '(none)') for r in rows))}")
pend = [r for r in rows if (r.get("decision") or "") == ""]
lines.append(
    f"Report pending (decision='') openai: {dict(Counter((r.get('openai') or '(none)') for r in pend))}"
)
lines.append(f"\nALL historical decision='accept' unique ids ({len(accepts)}):")
for r in sorted(accepts, key=lambda x: x["id"]):
    lines.append(
        f"id={r['id']} | video_id={r['video_id']} | start_sec={r['start_sec']} | "
        f"peak_score={r.get('old_peak_score')} | mean_score=N/A_in_report | "
        f"rank_score=N/A_in_report | best_cue={r.get('old_best_cue')} | "
        f"notes=openai:{r.get('openai')} | source_url={r.get('source_url')} | "
        f"new_score={r.get('new_score')} | passes_new_gate={r.get('passes_new_gate')}"
    )

out = ROOT / "output" / "_harden_audit.txt"
text = out.read_text(encoding="utf-8")
if "F) HISTORICAL SNAPSHOT" not in text:
    text = text.replace("END OF AUDIT\n", "\n".join(lines) + "\n\nEND OF AUDIT\n")
    out.write_text(text, encoding="utf-8")
    print(f"Appended historical section; new size={out.stat().st_size}")
else:
    print("Already present")
