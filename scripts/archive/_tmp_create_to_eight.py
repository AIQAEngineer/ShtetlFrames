"""Create pods up to want in THIS process (foreground create, soft wait)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env
import config as app_config
from runpod_client import set_pod_pool
from runpod_provision import (
    MAX_PARALLEL_PODS,
    count_active_shtetl_pods,
    ensure_pods,
    find_shtetl_pods,
    set_pod_create_ceiling,
    set_pod_creates_blocked,
)

load_env()
set_pod_creates_blocked(False)
set_pod_create_ceiling(None)
want = max(1, min(int(app_config.RUNPOD_MAX_INFLIGHT or 8), MAX_PARALLEL_PODS))
print(f"before active={count_active_shtetl_pods()} want={want}", flush=True)

def st(msg: str) -> None:
    low = (msg or "").lower()
    if any(k in low for k in ("creat", "ready", "only", "fail", "trim", "filling", "now")):
        print(f"  {msg}"[:180], flush=True)

bases = ensure_pods(count=want, on_status=st, min_ready=1, extra_fill_sec=0)
print(f"ensure ready={len(bases)} active={count_active_shtetl_pods()}", flush=True)
if bases:
    set_pod_pool(bases)

# Wait briefly for GraphQL to show creates from this soft pass.
for i in range(12):
    n = count_active_shtetl_pods()
    print(f"  poll active={n}/{want}", flush=True)
    if n >= want:
        break
    time.sleep(5)

print(
    f"FINAL active={count_active_shtetl_pods()} names={[p.get('name') for p in find_shtetl_pods()]}",
    flush=True,
)
