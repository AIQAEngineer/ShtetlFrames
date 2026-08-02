"""Compare prompt-only vs probe-blended scores on exported Keep/Pass stills."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402


def score_dir(label: str, folder: Path, scorer) -> list[tuple[str, float]]:
    out = []
    for p in sorted(folder.glob("*.jpg"))[:8]:
        img = Image.open(p).convert("RGB")
        s, pos, neg, cue = scorer.score_image(img)
        out.append((p.name, s, pos, neg))
        print(f"  {label:4} {p.name:28} score={s:+.4f} pos={pos:.3f} neg={neg:.3f}")
    return out


def main() -> None:
    from shtetl_core.scoring import CueScorer

    keep = ROOT / "output" / "clip_ft" / "dataset" / "keep"
    pas = ROOT / "output" / "clip_ft" / "dataset" / "pass"

    print("=== baseline (CLIP_PROBE=0) ===")
    os.environ["CLIP_PROBE"] = "0"
    base = CueScorer(device="cpu")
    assert base.probe is None, "probe should be disabled"
    score_dir("keep", keep, base)
    score_dir("pass", pas, base)

    print("\n=== probe blended ===")
    os.environ["CLIP_PROBE"] = "1"
    # Force re-resolve by new instance
    probe = CueScorer(device="cpu")
    print("probe_path", probe.probe_path, "blend", probe.probe_blend)
    assert probe.probe is not None, "probe should load"
    score_dir("keep", keep, probe)
    score_dir("pass", pas, probe)


if __name__ == "__main__":
    main()
