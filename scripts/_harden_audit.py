#!/usr/bin/env python3
"""Audit Review decisions + Munkacs candidates for gate hardening."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import DB_PATH  # noqa: E402

OUT = ROOT / "output" / "_harden_audit.txt"
MUNKACS_RE = re.compile(r"munkacs|munkács|munkatsh", re.I)


def openai_tag(notes: str | None) -> str:
    low = (notes or "").lower()
    if "openai:keep" in low or "vlm:keep" in low:
        return "keep"
    if "openai:drop" in low or "vlm:drop" in low:
        return "drop"
    if "openai:uncertain" in low or "vlm:uncertain" in low:
        return "uncertain"
    return "(none)"


def trunc(s: str | None, n: int = 200) -> str:
    t = (s or "").replace("\n", " ").replace("\r", " ")
    return t[:n]


def fmt_row(r: sqlite3.Row, *, with_decision: bool = False) -> str:
    parts = [
        f"id={r['id']}",
        f"video_id={r['video_id']}",
        f"start_sec={r['start_sec']}",
        f"peak_score={r['peak_score']}",
        f"mean_score={r['mean_score']}",
        f"rank_score={r['rank_score']}",
        f"best_cue={r['best_cue']}",
    ]
    if with_decision:
        parts.insert(1, f"decision={r['decision']!r}")
    parts.append(f"notes={trunc(r['notes'])!r}")
    parts.append(f"source_url={r['source_url']}")
    return " | ".join(str(p) for p in parts)


def summarize_rescore_json(path: Path) -> list[str]:
    lines: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"  ERROR reading {path.name}: {e}"]

    lines.append(f"=== {path.name} ===")

    # munkacs_still_rescore.json style: {rows:[{passes:...}]}
    if isinstance(data, dict) and "rows" in data and "summary" not in data:
        rows = data.get("rows") or []
        n = len(rows)
        n_pass = sum(1 for r in rows if r.get("passes"))
        n_fail = n - n_pass
        rate = (n_pass / n) if n else 0.0
        lines.append(f"  style: still_rescore rows")
        for k in ("min_head", "threshold", "min_pos", "score_threshold"):
            if k in data:
                lines.append(f"  {k}={data[k]}")
        lines.append(f"  n={n} pass={n_pass} fail={n_fail} keep/pass_rate={rate:.4f}")
        for r in rows:
            lines.append(
                f"    {r.get('name')}: score={r.get('score')} head={r.get('head')} "
                f"passes={r.get('passes')} cue={r.get('cue')}"
            )
        return lines

    # candidate_rescore_report.json style
    if isinstance(data, dict) and "summary" in data:
        s = data["summary"]
        lines.append("  style: candidate_rescore_report")
        for k in (
            "n_total",
            "n_scored",
            "n_skipped_no_still",
            "n_pass_new_gate",
            "n_fail_new_gate",
            "score_threshold",
            "min_pos_score",
            "min_headcover_score",
            "pass_rate",
        ):
            if k in s:
                lines.append(f"  {k}={s[k]}")
        if "by_decision_pass" in s:
            lines.append("  by_decision_pass:")
            for dec, st in s["by_decision_pass"].items():
                lines.append(f"    {dec!r}: {st}")
        if "by_openai_pass" in s:
            lines.append("  by_openai_pass:")
            for tag, st in s["by_openai_pass"].items():
                lines.append(f"    {tag!r}: {st}")
        # Munkacs subset in rows if present
        rows = data.get("rows") or []
        munk = [
            r
            for r in rows
            if MUNKACS_RE.search(
                " ".join(
                    str(r.get(k) or "")
                    for k in ("video_id", "source_url", "notes", "old_best_cue", "new_best_cue")
                )
            )
        ]
        if munk:
            n = len(munk)
            n_pass = sum(1 for r in munk if r.get("passes_new_gate"))
            lines.append(
                f"  munkacs-related rows in report: n={n} pass_new_gate={n_pass} "
                f"rate={n_pass/n if n else 0:.4f}"
            )
            for r in munk[:40]:
                lines.append(
                    f"    id={r.get('id')} decision={r.get('decision')!r} openai={r.get('openai')} "
                    f"old={r.get('old_peak_score')} new={r.get('new_score')} "
                    f"pass={r.get('passes_new_gate')} video={r.get('video_id')}"
                )
            if len(munk) > 40:
                lines.append(f"    ... +{len(munk)-40} more")
        return lines

    # Generic / demo JSON
    if isinstance(data, dict):
        keys = list(data.keys())[:30]
        lines.append(f"  top-level keys: {keys}")
        # try common keep fields
        if "keep" in data:
            lines.append(f"  keep={data.get('keep')}")
        if "results" in data and isinstance(data["results"], list):
            res = data["results"]
            n_keep = sum(1 for r in res if r.get("keep") or r.get("passes") or r.get("passes_new_gate"))
            lines.append(f"  results n={len(res)} keepish={n_keep}")
        return lines

    if isinstance(data, list):
        n = len(data)
        n_keep = sum(
            1
            for r in data
            if isinstance(r, dict)
            and (r.get("keep") or r.get("passes") or r.get("passes_new_gate"))
        )
        lines.append(f"  list n={n} keepish={n_keep}")
        return lines

    lines.append(f"  unrecognized JSON type: {type(data)}")
    return lines


def main() -> None:
    lines: list[str] = []
    lines.append("HARDEN AUDIT — Review decisions + Munkács candidates + current gates")
    lines.append("=" * 78)
    lines.append("")

    db_path = Path(DB_PATH)
    alt = ROOT / "output" / "shtetl.db"
    if not db_path.exists() and alt.exists():
        db_path = alt
        lines.append(f"NOTE: config DB_PATH missing; using {db_path}")
    lines.append(f"DB_PATH: {db_path}")
    lines.append(f"exists: {db_path.exists()}")
    lines.append("")

    if not db_path.exists():
        lines.append("ERROR: database not found")
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(OUT.read_text(encoding="utf-8"))
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Schema peek
    cols = [r[1] for r in conn.execute("PRAGMA table_info(candidates)").fetchall()]
    lines.append(f"candidates columns: {cols}")
    lines.append("")

    # 1) counts by decision
    lines.append("1) CANDIDATES BY DECISION")
    lines.append("-" * 40)
    dec_counts = Counter()
    for row in conn.execute("SELECT decision FROM candidates"):
        d = row["decision"]
        if d is None:
            key = "(null)"
        elif d == "":
            key = "'' (pending)"
        elif d in ("accept", "reject"):
            key = d
        else:
            key = f"other:{d!r}"
        dec_counts[key] += 1
    total = sum(dec_counts.values())
    lines.append(f"total candidates: {total}")
    for k, v in sorted(dec_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {k}: {v}")
    lines.append("")

    # Accept rows
    lines.append("2) ALL decision='accept' ROWS")
    lines.append("-" * 40)
    accepts = conn.execute(
        """
        SELECT id, video_id, start_sec, peak_score, mean_score, rank_score,
               best_cue, notes, source_url, decision
        FROM candidates
        WHERE decision = 'accept'
        ORDER BY id
        """
    ).fetchall()
    lines.append(f"count: {len(accepts)}")
    for r in accepts:
        lines.append(fmt_row(r))
    lines.append("")

    # Munkacs-related
    lines.append("3) MUNKÁCS / MUNKACS / MUNKATSH MENTIONS")
    lines.append("-" * 40)
    all_rows = conn.execute(
        """
        SELECT id, video_id, start_sec, peak_score, mean_score, rank_score,
               best_cue, notes, source_url, decision
        FROM candidates
        ORDER BY id
        """
    ).fetchall()
    munk = []
    for r in all_rows:
        blob = " ".join(
            str(r[k] or "") for k in ("video_id", "source_url", "notes", "best_cue")
        )
        if MUNKACS_RE.search(blob):
            munk.append(r)
    lines.append(f"count: {len(munk)}")
    munk_dec = Counter((r["decision"] or "") for r in munk)
    lines.append("by decision: " + ", ".join(f"{k!r}:{v}" for k, v in sorted(munk_dec.items())))
    for r in munk:
        lines.append(fmt_row(r, with_decision=True))
    lines.append("")

    # openai keep/drop
    lines.append("4) OPENAI/VLM KEEP VS DROP (ALL CANDIDATES)")
    lines.append("-" * 40)
    tag_counts = Counter(openai_tag(r["notes"]) for r in all_rows)
    for k, v in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("5) PENDING (decision='') — OPENAI KEEP VS DROP")
    lines.append("-" * 40)
    pending = [r for r in all_rows if (r["decision"] or "") == ""]
    pend_tags = Counter(openai_tag(r["notes"]) for r in pending)
    lines.append(f"pending total: {len(pending)}")
    for k, v in sorted(pend_tags.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {k}: {v}")
    lines.append("")

    # 2) rescore reports
    lines.append("6) OUTPUT/ MUNKACS + RESCORE REPORTS")
    lines.append("-" * 40)
    out_dir = ROOT / "output"
    patterns = [
        "*munkacs*",
        "*munkács*",
        "*rescore*",
        "*l14_munkacs*",
    ]
    seen: set[Path] = set()
    files: list[Path] = []
    for pat in patterns:
        for p in out_dir.glob(pat):
            if p.is_file() and p.suffix.lower() in (".json", ".csv", ".log", ".txt"):
                if p not in seen:
                    seen.add(p)
                    files.append(p)
    files = sorted(files, key=lambda p: p.name.lower())
    lines.append(f"matched files: {len(files)}")
    for p in files:
        lines.append(f"  - {p.name} ({p.stat().st_size} bytes)")
    lines.append("")

    for p in files:
        if p.suffix.lower() == ".json":
            lines.extend(summarize_rescore_json(p))
            lines.append("")
        elif p.suffix.lower() == ".csv" and "rescore" in p.name.lower():
            # quick pass/fail if column exists
            try:
                text = p.read_text(encoding="utf-8", errors="replace").splitlines()
                if not text:
                    continue
                header = text[0].split(",")
                lines.append(f"=== {p.name} (CSV) ===")
                lines.append(f"  header cols: {len(header)} rows: {len(text)-1}")
                # find passes column
                idx = None
                for i, h in enumerate(header):
                    if h.strip().lower() in (
                        "passes_new_gate",
                        "passes",
                        "pass",
                    ):
                        idx = i
                        break
                if idx is not None:
                    vals = []
                    for line in text[1:]:
                        # naive CSV split ok for this report
                        parts = line.split(",")
                        if len(parts) > idx:
                            vals.append(parts[idx].strip().lower())
                    n_true = sum(1 for v in vals if v in ("1", "true", "yes"))
                    n_false = sum(1 for v in vals if v in ("0", "false", "no"))
                    lines.append(
                        f"  passes col[{idx}]={header[idx]!r}: true={n_true} false={n_false}"
                    )
                lines.append("")
            except Exception as e:
                lines.append(f"=== {p.name} ERROR: {e} ===")
                lines.append("")

    # 3) current gates
    lines.append("7) CURRENT GATES — src/shtetl_core/cues.py")
    lines.append("-" * 40)
    try:
        import shtetl_core.cues as cues

        lines.append(f"CLIP_MODEL={cues.CLIP_MODEL} pretrained={cues.CLIP_PRETRAINED}")
        lines.append(f"DEFAULT_SCORE_THRESHOLD={cues.DEFAULT_SCORE_THRESHOLD}")
        lines.append(f"MIN_POS_SCORE={cues.MIN_POS_SCORE}")
        lines.append(f"MIN_HEADCOVER_SCORE={cues.MIN_HEADCOVER_SCORE}")
        lines.append(f"MIN_MALE_SCORE={cues.MIN_MALE_SCORE}")
        lines.append(f"MIN_BODY_SCORE={cues.MIN_BODY_SCORE}")
        lines.append(f"MAX_NEG_TO_POS_RATIO={cues.MAX_NEG_TO_POS_RATIO}")
        lines.append(f"NEG_SCORE_WEIGHT={cues.NEG_SCORE_WEIGHT}")
        lines.append(f"DEFAULT_FPS={cues.DEFAULT_FPS}")
        lines.append(f"MIN_SEGMENT_SEC={cues.MIN_SEGMENT_SEC}")
        lines.append(f"MAX_GAP_SEC={cues.MAX_GAP_SEC}")
        lines.append(f"MIN_PERSON_AREA={cues.MIN_PERSON_AREA}")
        lines.append(f"MIN_PERSON_ASPECT={cues.MIN_PERSON_ASPECT}")
        lines.append(f"MIN_PERSON_HEIGHT={cues.MIN_PERSON_HEIGHT}")
        lines.append(f"YOLO_CONF={cues.YOLO_CONF}")
        lines.append(f"TOP_K_CUES={cues.TOP_K_CUES} TOP_K_NEGS={cues.TOP_K_NEGS}")
        lines.append("")
        lines.append(f"POSITIVE_PROMPTS ({len(cues.POSITIVE_PROMPTS)}):")
        for p in cues.POSITIVE_PROMPTS:
            lines.append(f"  + {p}")
        lines.append(f"HEADCOVER_PROMPTS ({len(cues.HEADCOVER_PROMPTS)}):")
        for p in cues.HEADCOVER_PROMPTS:
            lines.append(f"  + {p}")
        lines.append(f"MALE_PROMPTS ({len(cues.MALE_PROMPTS)}):")
        for p in cues.MALE_PROMPTS:
            lines.append(f"  + {p}")
        lines.append(f"BODY_PROMPTS ({len(cues.BODY_PROMPTS)}):")
        for p in cues.BODY_PROMPTS:
            lines.append(f"  + {p}")
        lines.append(f"NEGATIVE_PROMPTS ({len(cues.NEGATIVE_PROMPTS)}) — first 8:")
        for p in cues.NEGATIVE_PROMPTS[:8]:
            lines.append(f"  - {p}")
        lines.append(f"  ... +{max(0, len(cues.NEGATIVE_PROMPTS)-8)} more")
    except Exception as e:
        lines.append(f"ERROR importing cues: {e}")
    lines.append("")

    lines.append("8) CURRENT GATES — src/openai_verify.py")
    lines.append("-" * 40)
    try:
        import openai_verify as ov

        lines.append(f"DEFAULT_MODEL={ov.DEFAULT_MODEL}")
        lines.append("KEEP RULES (code):")
        lines.append("  - KEEP only if keep=true AND looks_jewish=true AND head_covered=true")
        lines.append("  - Legacy replies missing looks_jewish/head_covered → fail closed (keep=false)")
        lines.append("  - Parse fallback: bare head keywords force keep=false")
        lines.append("  - notes tags: openai:keep | openai:drop | openai:uncertain (or vlm:)")
        lines.append("  - When verify enabled: errors/skips fail closed (keep=False)")
        lines.append("  - Cascade ollama_then_openai: OpenAI only runs if VLM keeps")
        lines.append("")
        lines.append("SYSTEM PROMPT (key reject/keep lines):")
        sys_prompt = ov._SYSTEM
        # pull key sentences
        for sentence in re.split(r"(?<=[.])\s+", sys_prompt):
            s = sentence.strip()
            if not s:
                continue
            low = s.lower()
            if any(
                k in low
                for k in (
                    "keep",
                    "reject",
                    "count as",
                    "hard reject",
                    "prefer keep",
                    "do not reject",
                    "head_covered",
                    "looks_jewish",
                    "face-only",
                    "male",
                )
            ):
                lines.append(f"  • {s}")
        lines.append("")
        lines.append("USER PROMPT:")
        for sentence in re.split(r"(?<=[.])\s+", ov._USER):
            s = sentence.strip()
            if s:
                lines.append(f"  • {s}")
    except Exception as e:
        lines.append(f"ERROR importing openai_verify: {e}")

    lines.append("")
    lines.append("END OF AUDIT")
    conn.close()

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} ({len(text)} chars)")
    # also print full for capture
    print(text)


if __name__ == "__main__":
    main()
