"""Sanity-check the locally saved probe.pt payload metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    probe = ROOT / "output" / "clip_ft" / "probe.pt"
    try:
        import torch
    except ImportError:
        print(json.dumps({"ok": False, "error": "torch not in venv"}))
        return
    payload = torch.load(probe, map_location="cpu", weights_only=False)
    out = {
        "ok": True,
        "keys": sorted(payload.keys()),
        "dim": payload.get("dim"),
        "clip_model": payload.get("clip_model"),
        "clip_pretrained": payload.get("clip_pretrained"),
        "blend": payload.get("blend"),
        "n_keep": payload.get("n_keep"),
        "n_pass": payload.get("n_pass"),
        "val_acc": payload.get("val_acc"),
        "epochs_ran": payload.get("epochs_ran"),
        "device_trained": payload.get("device"),
        "state_keys": sorted((payload.get("state_dict") or {}).keys()),
        "weight_shape": list(payload["state_dict"]["weight"].shape),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
