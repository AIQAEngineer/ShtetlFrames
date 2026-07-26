#!/usr/bin/env python3
"""Enrich harden audit with shtetl.db + fuller munkacs JSON summaries."""
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

MUNKACS_RE = re.compile(r"munkacs|munkács|munkatsh|munkatch", re.I)
OUT = ROOT / "output" / "_harden_audit.txt"


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


def audit_db(path: Path) -> list[str]:
    lines: list[str] = []
    lines.append(f"DB: {path}")
    lines.append(f"exists: {path.exists()} size={path.stat().st_size if path.exists() else 0}")
    if not path.exists():
        return lines
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    lines.append(f"tables: {tables}")
    if "candidates" not in tables:
        conn.close()
        return lines

    cols = [r[1] for r in conn.execute("PRAGMA table_info(candidates)").fetchall()]
    lines.append(f"columns: {cols}")

    dec_counts: Counter[str] = Counter()
    all_rows = conn.execute(
        """
        SELECT id, video_id, start_sec, peak_score, mean_score, rank_score,
               best_cue, notes, source_url, decision
        FROM candidates
        ORDER BY id
        """
    ).fetchall()
    for row in all_rows:
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

    lines.append(f"total candidates: {len(all_rows)}")
    for k, v in sorted(dec_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {k}: {v}")

    accepts = [r for r in all_rows if r["decision"] == "accept"]
    lines.append(f"\nALL decision='accept' ({len(accepts)}):")
    for r in accepts:
        lines.append(
            f"id={r['id']} | video_id={r['video_id']} | start_sec={r['start_sec']} | "
            f"peak_score={r['peak_score']} | mean_score={r['mean_score']} | "
            f"rank_score={r['rank_score']} | best_cue={r['best_cue']} | "
            f"notes={trunc(r['notes'])!r} | source_url={r['source_url']}"
        )

    munk = []
    for r in all_rows:
        blob = " ".join(
            str(r[k] or "") for k in ("video_id", "source_url", "notes", "best_cue")
        )
        if MUNKACS_RE.search(blob):
            munk.append(r)
    lines.append(f"\nMUNKACS/MUNKÁCS/MUNKATSH/MUNKATCH mentions ({len(munk)}):")
    munk_dec = Counter((r["decision"] or "") for r in munk)
    lines.append(
        "by decision: " + ", ".join(f"{k!r}:{v}" for k, v in sorted(munk_dec.items()))
    )
    for r in munk:
        lines.append(
            f"id={r['id']} | decision={r['decision']!r} | video_id={r['video_id']} | "
            f"start_sec={r['start_sec']} | peak_score={r['peak_score']} | "
            f"mean_score={r['mean_score']} | rank_score={r['rank_score']} | "
            f"best_cue={r['best_cue']} | notes={trunc(r['notes'])!r} | "
            f"source_url={r['source_url']}"
        )

    tag_counts = Counter(openai_tag(r["notes"]) for r in all_rows)
    lines.append("\nopenai/vlm keep vs drop (all):")
    for k, v in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {k}: {v}")

    pending = [r for r in all_rows if (r["decision"] or "") == ""]
    pend_tags = Counter(openai_tag(r["notes"]) for r in pending)
    lines.append(f"\npending decision='' ({len(pending)}) openai/vlm:")
    for k, v in sorted(pend_tags.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {k}: {v}")

    # list keeps for current small DB usefulness
    keeps = [r for r in all_rows if openai_tag(r["notes"]) == "keep"]
    lines.append(f"\nopenai/vlm:keep rows ({len(keeps)}):")
    for r in keeps:
        lines.append(
            f"id={r['id']} | decision={r['decision']!r} | video_id={r['video_id']} | "
            f"start_sec={r['start_sec']} | peak={r['peak_score']} | "
            f"notes={trunc(r['notes'])!r} | source_url={r['source_url']}"
        )

    conn.close()
    return lines


def summarize_munkacs_files() -> list[str]:
    lines: list[str] = []
    # l14
    p = ROOT / "output" / "l14_munkacs_and_rejects.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        lines.append("=== l14_munkacs_and_rejects.json (detail) ===")
        pos = data.get("munkacs_positive") or {}
        segs = pos.get("segments") or []
        lines.append(
            f"munkacs_positive: url={pos.get('url')} n_hits={pos.get('n_hits')} "
            f"model={pos.get('model')} segments={len(segs)}"
        )
        for s in segs:
            lines.append(
                f"  peak={s.get('peak_score')} t={s.get('start_sec')}-{s.get('end_sec')} "
                f"cue={s.get('best_cue')}"
            )
        for key, val in data.items():
            if key == "munkacs_positive":
                continue
            lines.append(
                f"{key}: n_hits={val.get('n_hits')} old_peak={val.get('old_peak')} "
                f"url={val.get('url')}"
            )
        lines.append("")

    p = ROOT / "output" / "munkacs_runpod_demo.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        lines.append("=== munkacs_runpod_demo.json (detail) ===")
        lines.append(
            f"ok={data.get('ok')} phase={data.get('phase')} duration={data.get('duration')} "
            f"n_hits={data.get('n_hits')} n_segments={data.get('n_segments')} "
            f"peak_score={data.get('peak_score')} flagged={data.get('flagged')} "
            f"elapsed_sec={data.get('elapsed_sec')}"
        )
        segs = data.get("segments") or []
        lines.append(f"segments ({len(segs)}) — all would be keeps at CLIP stage:")
        for s in segs:
            lines.append(
                f"  t={s.get('start_sec')}-{s.get('end_sec')} peak={s.get('peak_score')} "
                f"mean={s.get('mean_score')} cue={s.get('best_cue')}"
            )
        lines.append(
            f"KEEP RATE (CLIP demo): {len(segs)}/{len(segs)} segments flagged "
            f"(n_hits={data.get('n_hits')})"
        )
        lines.append("")

    p = ROOT / "output" / "munkacs_still_rescore.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data.get("rows") or []
        n_pass = sum(1 for r in rows if r.get("passes"))
        lines.append("=== munkacs_still_rescore.json keep rate ===")
        lines.append(
            f"gates used: threshold={data.get('threshold')} min_head={data.get('min_head')}"
        )
        lines.append(
            f"n={len(rows)} pass={n_pass} fail={len(rows)-n_pass} "
            f"pass_rate={n_pass/len(rows) if rows else 0:.4f}"
        )
        lines.append(
            "NOTE: these gates (thr=0.1, min_head=0.25) are STRICTER than current code "
            "(thr=0.04, MIN_HEADCOVER=0.16)."
        )
        lines.append("")

    # candidate report munkacs subset with munkatch spelling
    p = ROOT / "output" / "candidate_rescore_report.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
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
        lines.append("=== candidate_rescore_report.json Munkács subset ===")
        lines.append(
            f"NOTE: report reflects a prior larger DB snapshot (n_total="
            f"{(data.get('summary') or {}).get('n_total')}), not necessarily current DB."
        )
        n = len(munk)
        n_pass = sum(1 for r in munk if r.get("passes_new_gate"))
        lines.append(
            f"munkacs-related scored rows: n={n} pass_new_gate={n_pass} "
            f"rate={n_pass/n if n else 0:.4f}"
        )
        dec = Counter((r.get("decision") or "") for r in munk)
        oai = Counter((r.get("openai") or "") for r in munk)
        lines.append(f"by decision: {dict(dec)}")
        lines.append(f"by openai tag: {dict(oai)}")
        for r in munk:
            lines.append(
                f"  id={r.get('id')} decision={r.get('decision')!r} openai={r.get('openai')} "
                f"old={r.get('old_peak_score')} new={r.get('new_score')} "
                f"pass={r.get('passes_new_gate')} t={r.get('start_sec')} "
                f"video={r.get('video_id')}"
            )
        s = data.get("summary") or {}
        lines.append("")
        lines.append(
            f"Overall rescore keep/pass rate at thr={s.get('score_threshold')} "
            f"min_pos={s.get('min_pos_score')} min_head={s.get('min_headcover_score')}: "
            f"{s.get('n_pass_new_gate')}/{s.get('n_scored')} = {s.get('pass_rate')}"
        )
        # accept survivors
        acc = (s.get("by_decision_pass") or {}).get("accept") or {}
        lines.append(
            f"Among historical accept rows in report: pass={acc.get('pass')} "
            f"fail={acc.get('fail')} (only 1/12 accepts survive thr=0.08 gate — TP risk)"
        )
        lines.append("")

    return lines


def main() -> None:
    lines: list[str] = []
    lines.append("HARDEN AUDIT — Review decisions + Munkács candidates + current gates")
    lines.append("=" * 78)
    lines.append("")
    lines.append(
        "IMPORTANT: config DB_PATH is output/shtetlframes.db. "
        "A separate output/shtetl.db may exist. Both are audited below. "
        "Rescore reports may reflect an older/larger DB snapshot."
    )
    lines.append("")

    lines.append("=" * 78)
    lines.append("A) PRIMARY DB (config.DB_PATH)")
    lines.append("=" * 78)
    lines.extend(audit_db(Path(DB_PATH)))
    lines.append("")

    alt = ROOT / "output" / "shtetl.db"
    if alt.resolve() != Path(DB_PATH).resolve():
        lines.append("=" * 78)
        lines.append("B) ALTERNATE DB output/shtetl.db")
        lines.append("=" * 78)
        lines.extend(audit_db(alt))
        lines.append("")

    lines.append("=" * 78)
    lines.append("C) OUTPUT/ MUNKACS + RESCORE KEEP RATES")
    lines.append("=" * 78)
    lines.extend(summarize_munkacs_files())

    # gates (same as before)
    lines.append("=" * 78)
    lines.append("D) CURRENT GATES — src/shtetl_core/cues.py")
    lines.append("=" * 78)
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
    lines.append(f"FACE_ONLY_PROMPTS ({len(cues.FACE_ONLY_PROMPTS)}):")
    for p in cues.FACE_ONLY_PROMPTS:
        lines.append(f"  - {p}")
    lines.append(f"NEGATIVE_PROMPTS ({len(cues.NEGATIVE_PROMPTS)}):")
    for p in cues.NEGATIVE_PROMPTS:
        lines.append(f"  - {p}")
    lines.append("")

    lines.append("=" * 78)
    lines.append("E) CURRENT GATES — src/openai_verify.py")
    lines.append("=" * 78)
    import openai_verify as ov

    lines.append(f"DEFAULT_MODEL={ov.DEFAULT_MODEL}")
    lines.append("KEEP RULES (code):")
    lines.append("  - KEEP only if keep=true AND looks_jewish=true AND head_covered=true")
    lines.append("  - Legacy replies missing looks_jewish/head_covered → fail closed (keep=false)")
    lines.append("  - Parse fallback: bare head keywords force keep=false")
    lines.append("  - notes tags: openai:keep | openai:drop | openai:uncertain (or vlm:)")
    lines.append("  - When verify enabled: errors/skips fail closed (keep=False)")
    lines.append("  - Cascade ollama_then_openai: OpenAI only runs if VLM keeps")
    lines.append("  - verify_stills_any: try up to 3 nearby stills; keep if any keep")
    lines.append("")
    lines.append("SYSTEM PROMPT (key reject/keep lines):")
    for sentence in re.split(r"(?<=[.])\s+", ov._SYSTEM):
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
    lines.append("")
    lines.append("END OF AUDIT")

    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} ({len(text)} chars, {len(lines)} lines)")


if __name__ == "__main__":
    main()
