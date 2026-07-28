"""Deep-sample Keep/Pass feedback frames, train CLIP probe, optional YOLO cls export.

This machine has no local NVIDIA GPU (torch CPU). Encoding uses CUDA when
available; otherwise CPU. For GPU: start a RunPod scrape pod and use
``scripts/train_clip_on_runpod.py`` after deep export, or rely on CPU here.

Usage:
  .\\.venv\\Scripts\\python.exe scripts\\retrain_from_feedback.py
  .\\.venv\\Scripts\\python.exe scripts\\retrain_from_feedback.py --export-only
  .\\.venv\\Scripts\\python.exe scripts\\retrain_from_feedback.py --yolo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export-only", action="store_true", help="Deep sample only")
    ap.add_argument("--shallow", action="store_true", help="One still per label (old)")
    ap.add_argument("--yolo", action="store_true", help="Also export YOLO cls dataset")
    ap.add_argument("--device", default=None, help="cuda|cpu (default: auto)")
    args = ap.parse_args()

    def status(msg: str) -> None:
        print(msg, flush=True)

    from clip_ft import (
        export_and_train,
        export_keep_pass_dataset,
        export_keep_pass_dataset_deep,
        train_linear_probe,
    )

    if args.export_only:
        if args.shallow:
            result = export_keep_pass_dataset(on_status=status)
        else:
            result = export_keep_pass_dataset_deep(on_status=status)
        print(json.dumps(result, indent=2, default=str))
        if not result.get("ok"):
            raise SystemExit(1)
    else:
        result = export_and_train(
            on_status=status, deep=not args.shallow, device=args.device
        )
        print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2, default=str))
        if not result.get("ok"):
            raise SystemExit(1)

    if args.yolo:
        sys.path.insert(0, str(ROOT / "scripts"))
        from export_yolo_feedback import export_yolo_cls_dataset

        y = export_yolo_cls_dataset(on_status=status)
        print(json.dumps(y, indent=2, default=str))
        if not y.get("ok"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
