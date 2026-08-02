"""List live shtetl pods and health-check each one's HTTP endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env  # noqa: E402

load_env()

import requests  # noqa: E402
from runpod_provision import find_shtetl_pods, pod_proxy_url  # noqa: E402


def main() -> None:
    pods = find_shtetl_pods()
    out = []
    for p in pods:
        pid = p.get("id") or ""
        base = pod_proxy_url(pid).rstrip("/")
        row = {
            "id": pid,
            "name": p.get("name"),
            "desiredStatus": p.get("desiredStatus"),
            "base": base,
        }
        try:
            r = requests.get(f"{base}/health", timeout=30)
            row["http"] = r.status_code
            body = r.json() if r.content else {}
            row["ok"] = body.get("ok")
            row["models_ready"] = body.get("models_ready")
            row["device"] = body.get("device")
            row["inflight"] = body.get("inflight")
        except Exception as e:
            row["error"] = str(e)[:200]
        out.append(row)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
