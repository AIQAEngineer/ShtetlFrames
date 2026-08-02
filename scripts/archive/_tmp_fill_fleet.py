"""Create missing pods up to RUNPOD_MAX_INFLIGHT (non-blocking soft fill)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env
import config as app_config
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
print(f"before active={count_active_shtetl_pods()} graphql={len(find_shtetl_pods())} want={want}", flush=True)

def st(msg: str) -> None:
    print(f"  {msg}"[:160], flush=True)

bases = ensure_pods(count=want, on_status=st, min_ready=1, extra_fill_sec=0)
print(f"ready_now={len(bases)} active={count_active_shtetl_pods()}", flush=True)
for b in bases:
    print(f"  {b}", flush=True)
