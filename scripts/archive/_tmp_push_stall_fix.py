"""Push local worker code (stall-fix handler.py) to every shtetl pod, per-pod report."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests
from config import load_env
from runpod_client import _local_worker_files_for_push
from runpod_provision import find_shtetl_pods, pod_proxy_url

load_env()

pods = find_shtetl_pods()
print(f"graphql pods: {len(pods)}", flush=True)
files = _local_worker_files_for_push()
print(f"files to push: {sorted(files)}", flush=True)

for pod in pods:
    pid = pod.get("id") or ""
    name = pod.get("name") or pid[:12]
    if not pid:
        continue
    base = pod_proxy_url(pid).rstrip("/")
    try:
        pr = requests.post(f"{base}/sync_push", json={"files": files}, timeout=120)
        try:
            body = pr.json() if pr.content else {}
        except Exception:
            body = {"raw": (pr.text or "")[:200]}
        if isinstance(body, dict):
            body.pop("files_b64", None)
            detail = f"ok={body.get('ok')} changed={body.get('changed')} reloaded={body.get('reloaded')} err={body.get('error')}"
        else:
            detail = str(body)[:160]
        print(f"PUSH {name} http={pr.status_code} {detail}"[:300], flush=True)
    except Exception as e:
        print(f"PUSH {name} ERROR {str(e)[:200]}", flush=True)
