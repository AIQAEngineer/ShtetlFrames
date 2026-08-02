"""Find tightest threshold/blend that still clears all Review Keep stills."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402
from PIL import Image  # noqa: E402

from config import CONTACT_DIR, load_env  # noqa: E402
from db import db, init_db  # noqa: E402
from settings_store import apply_settings_to_environ  # noqa: E402
from shtetl_core.cues import DEFAULT_SCORE_THRESHOLD  # noqa: E402
from shtetl_core.scoring import CueScorer  # noqa: E402


def keep_still_paths() -> list[Path]:
    """Review Keep stills only (contact sheets for decision=accept)."""
    init_db()
    paths: list[Path] = []
    with db() as c:
        rows = c.execute(
            "SELECT id FROM candidates WHERE decision='accept' ORDER BY id"
        ).fetchall()
    for r in rows:
        p = CONTACT_DIR / f"cand_{int(r['id'])}.jpg"
        if p.is_file() and p.stat().st_size > 200:
            paths.append(p)
    return paths


def score_with_blend(scorer: CueScorer, img: Image.Image, blend: float) -> float:
    """Recompute blended score with a temporary blend (same clamps)."""
    old = scorer.probe_blend
    scorer.probe_blend = float(blend)
    try:
        score, _, _, _ = scorer.score_image(img)
        return float(score)
    finally:
        scorer.probe_blend = old


def main() -> int:
    load_env()
    apply_settings_to_environ()
    load_env()

    all_paths = keep_still_paths()
    if not all_paths:
        print("No Keep stills found", flush=True)
        return 1

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(
        f"labeled_keeps={len(all_paths)} device={device} "
        f"baseline_thr={DEFAULT_SCORE_THRESHOLD}",
        flush=True,
    )
    scorer = CueScorer(device=device)
    print(
        f"probe={scorer.probe_path} current_blend={scorer.probe_blend} "
        f"probe_loaded={scorer.probe is not None}",
        flush=True,
    )
    if scorer.probe is None:
        print("ERROR: probe not loaded — cannot sweep", flush=True)
        return 1

    # Only protect Keeps that already clear today's gate. Others are clamped
    # (strong-neg / headcover) and cannot be saved by raising threshold.
    baseline_b = float(scorer.probe_blend or 0.5)
    viable: list[Path] = []
    already_fail: list[dict] = []
    for p in all_paths:
        s = score_with_blend(scorer, Image.open(p).convert("RGB"), baseline_b)
        if s >= float(DEFAULT_SCORE_THRESHOLD):
            viable.append(p)
        else:
            already_fail.append({"path": p.name, "score": round(s, 4)})
    print(
        f"viable_keeps={len(viable)} already_below_gate={len(already_fail)}",
        flush=True,
    )
    for row in already_fail:
        print(f"  skip {row['path']} score={row['score']}", flush=True)
    paths = viable
    if not paths:
        print("No viable Keep stills above current threshold", flush=True)
        return 1

    blends = [0.5, 0.6, 0.7, 0.75, 0.8]
    # Precompute scores per blend for each keep.
    scores_by_blend: dict[float, list[float]] = {}
    for b in blends:
        vals: list[float] = []
        for p in paths:
            img = Image.open(p).convert("RGB")
            vals.append(score_with_blend(scorer, img, b))
        scores_by_blend[b] = vals
        print(
            f"blend={b:.2f} min={min(vals):.4f} p10={sorted(vals)[max(0,len(vals)//10)]:.4f} "
            f"median={sorted(vals)[len(vals)//2]:.4f} max={max(vals):.4f}",
            flush=True,
        )

    # Candidate thresholds: from current up in fine steps, plus just-below keep mins.
    thr_candidates = [0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12]

    best = None  # maximize (threshold, blend) lexicographically
    rows = []
    for b in blends:
        vals = scores_by_blend[b]
        keep_min = min(vals)
        for thr in thr_candidates:
            n_ok = sum(1 for s in vals if s >= thr)
            ok = n_ok == len(vals)
            rows.append(
                {
                    "blend": b,
                    "threshold": thr,
                    "n_ok": n_ok,
                    "n_keep": len(vals),
                    "keep_min": keep_min,
                    "ok": ok,
                }
            )
            if ok:
                cand = (thr, b, keep_min)
                if best is None or cand[0] > best[0] or (
                    cand[0] == best[0] and cand[1] > best[1]
                ):
                    best = cand

    # Also try threshold just under keep_min for each blend (max safe thr).
    for b in blends:
        vals = scores_by_blend[b]
        keep_min = min(vals)
        # Floor to 3 decimals, leave tiny margin so float noise doesn't drop a keep.
        thr = max(0.04, round(keep_min - 0.005, 3))
        n_ok = sum(1 for s in vals if s >= thr)
        ok = n_ok == len(vals)
        rows.append(
            {
                "blend": b,
                "threshold": thr,
                "n_ok": n_ok,
                "n_keep": len(vals),
                "keep_min": keep_min,
                "ok": ok,
                "derived": True,
            }
        )
        if ok:
            cand = (thr, b, keep_min)
            if best is None or cand[0] > best[0] or (
                cand[0] == best[0] and cand[1] > best[1]
            ):
                best = cand

    out = {
        "n_labeled_keeps": len(all_paths),
        "n_viable_keeps": len(paths),
        "already_below_gate": already_fail,
        "baseline_threshold": DEFAULT_SCORE_THRESHOLD,
        "baseline_blend": float(scorer.probe_blend),
        "best": None
        if best is None
        else {
            "threshold": best[0],
            "blend": best[1],
            "keep_min_score": best[2],
            "margin": round(best[2] - best[0], 4),
        },
        "grid": rows,
    }
    out_path = ROOT / "output" / "clip_ft" / "keep_safe_sweep.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out["best"], indent=2), flush=True)
    print(f"wrote {out_path}", flush=True)

    if best is None:
        print("No setting retained all keeps", flush=True)
        return 1

    thr, blend, keep_min = best
    # Apply threshold to cues.py
    cues = ROOT / "src" / "shtetl_core" / "cues.py"
    text = cues.read_text(encoding="utf-8")
    old = f"DEFAULT_SCORE_THRESHOLD = {DEFAULT_SCORE_THRESHOLD}"
    # Handle float formatting variants
    import re

    text2, n = re.subn(
        r"^DEFAULT_SCORE_THRESHOLD\s*=\s*[0-9.]+",
        f"DEFAULT_SCORE_THRESHOLD = {thr}",
        text,
        count=1,
        flags=re.M,
    )
    if n != 1:
        print("WARN: could not patch cues.py threshold", flush=True)
    else:
        cues.write_text(text2, encoding="utf-8")
        print(f"patched cues.py DEFAULT_SCORE_THRESHOLD -> {thr}", flush=True)

    # Apply blend into probe.pt
    probe_path = Path(scorer.probe_path) if scorer.probe_path else None
    if probe_path and probe_path.is_file():
        try:
            payload = torch.load(probe_path, map_location="cpu", weights_only=False)
        except TypeError:
            payload = torch.load(probe_path, map_location="cpu")
        payload["blend"] = float(blend)
        payload["keep_safe_threshold"] = float(thr)
        payload["keep_safe_min_score"] = float(keep_min)
        torch.save(payload, probe_path)
        mirror = ROOT / "runpod_worker" / "clip_ft" / "probe.pt"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(probe_path, mirror)
        print(f"updated probe blend -> {blend} ({probe_path})", flush=True)

    # Sync worker cues copy if present
    worker_cues = ROOT / "runpod_worker" / "shtetl_core" / "cues.py"
    if worker_cues.is_file():
        wt = worker_cues.read_text(encoding="utf-8")
        wt2, n = re.subn(
            r"^DEFAULT_SCORE_THRESHOLD\s*=\s*[0-9.]+",
            f"DEFAULT_SCORE_THRESHOLD = {thr}",
            wt,
            count=1,
            flags=re.M,
        )
        if n == 1:
            worker_cues.write_text(wt2, encoding="utf-8")
            print("patched runpod_worker shtetl_core/cues.py", flush=True)

    print(
        f"APPLIED threshold={thr} blend={blend} "
        f"(keep_min={keep_min:.4f}, margin={keep_min-thr:.4f})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
