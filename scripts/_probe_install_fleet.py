"""Install the freshly trained output/clip_ft/probe.pt on every live shtetl pod."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env  # noqa: E402

load_env()

from runpod_client import push_clip_probe_to_pods  # noqa: E402


def main() -> None:
    probe = ROOT / "output" / "clip_ft" / "probe.pt"
    raw = probe.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    print(f"[install] local probe {probe} bytes={len(raw)} sha256={sha[:16]}")

    result = push_clip_probe_to_pods(force=True)
    print(json.dumps(result, indent=2, default=str)[:4000])

    n_ok = 0
    for row in result.get("results") or []:
        body = row.get("body") or {}
        if isinstance(body, dict) and body.get("ok") and body.get("bytes") == len(raw):
            n_ok += 1
    print(f"[install] pods confirmed ok with matching bytes: {n_ok}")


if __name__ == "__main__":
    main()
