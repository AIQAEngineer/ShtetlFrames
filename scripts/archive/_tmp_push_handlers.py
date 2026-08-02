"""Push current worker_sync (+ handlers) to all live shtetl pods; clear ollama 404."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env
from runpod_client import _ensure_local_handler
from runpod_provision import find_shtetl_pods, pod_proxy_url

load_env()


def st(msg: str) -> None:
    print(msg[:160], flush=True)


ok = 0
fail = 0
for p in find_shtetl_pods():
    pid = p.get("id") or ""
    name = p.get("name") or pid[:12]
    base = pod_proxy_url(pid).rstrip("/")
    if not base:
        print(f"SKIP {name} no proxy", flush=True)
        fail += 1
        continue
    try:
        pushed = _ensure_local_handler(base, on_status=st)
        print(f"{'OK' if pushed else 'FAIL'} {name} {base}", flush=True)
        ok += int(bool(pushed))
        fail += int(not pushed)
    except Exception as e:
        print(f"ERR {name}: {e}"[:160], flush=True)
        fail += 1
print(f"DONE ok={ok} fail={fail}", flush=True)
