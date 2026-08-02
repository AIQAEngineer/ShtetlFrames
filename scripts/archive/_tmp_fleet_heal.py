"""Terminate dead shtetl pods and refill to RUNPOD_MAX_INFLIGHT."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests
from config import load_env
import config as app_config
from runpod_client import (
    _classify_pod,
    maintain_pod_pool,
    set_pod_pool,
    get_pod_pool,
)
from runpod_provision import (
    MAX_PARALLEL_PODS,
    ensure_pods,
    find_shtetl_pods,
    pod_proxy_url,
    set_pod_create_ceiling,
    set_pod_creates_blocked,
    terminate_pod,
)

load_env()
set_pod_creates_blocked(False)
set_pod_create_ceiling(None)

want = max(1, min(int(app_config.RUNPOD_MAX_INFLIGHT or 8), MAX_PARALLEL_PODS))
print(f"want={want}", flush=True)

# 1) Kill sustained dead pods (ports up + HTTP dead, or EXITED/FAILED).
killed = 0
for p in find_shtetl_pods():
    pid = p.get("id")
    if not pid:
        continue
    name = p.get("name") or pid[:12]
    status = (p.get("desiredStatus") or "").upper()
    rt = p.get("runtime") if isinstance(p.get("runtime"), dict) else {}
    ports = (rt or {}).get("ports") or []
    try:
        uptime = float((rt or {}).get("uptimeInSeconds") or 0.0)
    except (TypeError, ValueError):
        uptime = 0.0
    base = pod_proxy_url(pid).rstrip("/")
    kind = _classify_pod(base)
    # EXITED/FAILED ghosts
    if status in ("EXITED", "FAILED", "TERMINATED"):
        print(f"kill {name} status={status}", flush=True)
        try:
            terminate_pod(pid)
            killed += 1
        except Exception as e:
            print(f"  terminate fail: {e}"[:160], flush=True)
        continue
    # Ports exist + dead HTTP for >3 min → zombie
    if ports and kind in ("dead", "broken") and uptime >= 180:
        print(f"kill {name} kind={kind} up={uptime:.0f}s ports={len(ports)}", flush=True)
        try:
            terminate_pod(pid)
            killed += 1
        except Exception as e:
            print(f"  terminate fail: {e}"[:160], flush=True)
        continue
    # No ports + RUNNING for >20 min with 404 → stuck bootstrap
    if not ports and status == "RUNNING" and uptime >= 1200:
        print(f"kill {name} stuck no-ports up={uptime:.0f}s", flush=True)
        try:
            terminate_pod(pid)
            killed += 1
        except Exception as e:
            print(f"  terminate fail: {e}"[:160], flush=True)

print(f"killed={killed}", flush=True)
time.sleep(3)

# 2) Ensure fleet
print("ensure_pods…", flush=True)

def _status(msg: str) -> None:
    print(f"  {msg}"[:160], flush=True)

bases = ensure_pods(
    count=want,
    on_status=_status,
    min_ready=1,
    extra_fill_sec=0,
)
print(f"ensure returned {len(bases)} ready", flush=True)
if bases:
    set_pod_pool(bases)

# 3) Maintain pass (adopt + fill)
alive = maintain_pod_pool(target=want, on_status=_status)
print(f"maintain alive={len(alive)} pool={len(get_pod_pool())}", flush=True)

# 4) Final probe
time.sleep(2)
pods = find_shtetl_pods()
ok = 0
for p in pods:
    pid = p.get("id")
    base = pod_proxy_url(pid).rstrip("/")
    try:
        r = requests.get(base + "/health", timeout=6)
        d = r.json() if r.status_code == 200 and r.content else {}
        good = bool(d.get("ok") and d.get("models_ready"))
    except Exception:
        good = False
    if good:
        ok += 1
    print(f"  {p.get('name')} healthy={good}", flush=True)
print(f"FINAL healthy={ok}/{len(pods)} want={want}", flush=True)
