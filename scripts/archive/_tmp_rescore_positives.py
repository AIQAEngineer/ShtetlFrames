"""Rescore human Keep (decision=accept) stills; they must still clear CLIP/OpenAI."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import OUTPUT_DIR, load_env
from db import db, init_db
from openai_verify import (
    openai_verify_enabled,
    verify_stills_any,
    verdict_is_keep,
)
from shtetl_core.cues import DEFAULT_SCORE_THRESHOLD
from shtetl_core.scoring import CueScorer
from still_store import candidate_still_path

OUT = OUTPUT_DIR / "positive_rescore_report.json"


def _load_pil(cand_id: int, image_url: str | None):
    from PIL import Image

    path = candidate_still_path(cand_id)
    if path.is_file() and path.stat().st_size > 200:
        return Image.open(path).convert("RGB"), path
    url = (image_url or "").strip()
    if url.startswith(("http://", "https://")):
        import requests
        from io import BytesIO

        r = requests.get(url, timeout=45)
        if r.status_code == 200 and len(r.content) > 200:
            return Image.open(BytesIO(r.content)).convert("RGB"), None
    return None, None


def main() -> int:
    load_env()
    init_db()
    with db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, video_id, peak_score, best_cue, decision, notes, image_url "
                "FROM candidates WHERE decision='accept' ORDER BY id ASC"
            ).fetchall()
        ]
    print(f"positive_count={len(rows)} thr={DEFAULT_SCORE_THRESHOLD}", flush=True)
    if not rows:
        print("NO_POSITIVES", flush=True)
        OUT.write_text(json.dumps({"summary": {"n": 0}, "misses": []}, indent=2))
        return 0

    scorer = CueScorer()
    thr = float(DEFAULT_SCORE_THRESHOLD)
    do_openai = openai_verify_enabled()
    misses: list[dict] = []
    ok_n = 0
    skip_n = 0
    clip_miss_n = 0
    openai_miss_n = 0

    for i, d in enumerate(rows, 1):
        cid = int(d["id"])
        img, still_path = _load_pil(cid, d.get("image_url"))
        if img is None:
            skip_n += 1
            print(f"[{i}/{len(rows)}] #{cid} SKIP no_still", flush=True)
            continue
        score, pos, neg, cue = scorer.score_image(img)
        clip_pass = score >= thr
        row = {
            "id": cid,
            "video_id": d.get("video_id"),
            "old_peak": d.get("peak_score"),
            "old_cue": d.get("best_cue"),
            "new_score": round(float(score), 4),
            "pos": round(float(pos), 4),
            "neg": round(float(neg), 4),
            "cue": cue,
            "clip_gate_pass": clip_pass,
            "openai_keep": None,
            "ok": True,
        }
        if not clip_pass:
            clip_miss_n += 1
            row["ok"] = False
            print(
                f"[{i}/{len(rows)}] #{cid} CLIP_MISS score={score:.3f} cue={(cue or '')[:60]}",
                flush=True,
            )
        else:
            print(
                f"[{i}/{len(rows)}] #{cid} clip_ok score={score:.3f}",
                flush=True,
            )

        if do_openai and still_path is not None:
            try:
                v = verify_stills_any([still_path], max_attempts=2)
                keep = verdict_is_keep(v)
                row["openai_keep"] = keep
                row["openai_marker"] = (v or {}).get("marker")
                row["openai_reason"] = str((v or {}).get("reason") or "")[:120]
                if not keep:
                    openai_miss_n += 1
                    row["ok"] = False
                    print(
                        f"  OPENAI_MISS marker={row['openai_marker']} "
                        f"{row['openai_reason']}",
                        flush=True,
                    )
            except Exception as e:
                row["openai_error"] = str(e)[:160]
                print(f"  openai_err {e}"[:160], flush=True)

        if row["ok"]:
            ok_n += 1
        else:
            misses.append(row)

    summary = {
        "ts": int(time.time()),
        "n_positives": len(rows),
        "n_scored": len(rows) - skip_n,
        "n_skip_no_still": skip_n,
        "n_still_ok": ok_n,
        "n_clip_miss": clip_miss_n,
        "n_openai_miss": openai_miss_n,
        "n_misses": len(misses),
        "score_threshold": thr,
        "openai_enabled": do_openai,
        "all_positives_still_pass": len(misses) == 0 and (len(rows) - skip_n) > 0,
    }
    OUT.write_text(
        json.dumps({"summary": summary, "misses": misses}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary), flush=True)
    print(f"wrote {OUT}", flush=True)
    return 0 if summary["all_positives_still_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
