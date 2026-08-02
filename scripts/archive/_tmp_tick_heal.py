"""One-shot fleet heal: clear ceiling, ensure 8, push handlers, report Ops health."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests
from config import load_env
import config as app_config
from runpod_client import (
    _ensure_local_handler,
    maintain_pod_pool,
    set_pod_pool,
)
from runpod_provision import (
    MAX_PARALLEL_PODS,
    count_active_shtetl_pods,
    ensure_pods,
    find_shtetl_pods,
    pod_proxy_url,
    set_pod_create_ceiling,
    set_pod_creates_blocked,
    shtetl_hard_cap,
)

load_env()
set_pod_creates_blocked(False)
set_pod_create_ceiling(None)
want = max(1, min(int(app_config.RUNPOD_MAX_INFLIGHT or 8), MAX_PARALLEL_PODS))


def st(msg: str) -> None:
    low = (msg or "").lower()
    if any(k in low for k in ("creat", "ready", "trim", "fail", "only", "push", "surplus")):
        print(f"  {msg}"[:180], flush=True)


print(
    f"heal start active={count_active_shtetl_pods()} hard_cap={shtetl_hard_cap()} want={want}",
    flush=True,
)
bases = ensure_pods(count=want, on_status=st, min_ready=1, extra_fill_sec=0)
if bases:
    set_pod_pool(bases)
maintain_pod_pool(target=want, on_status=st)

ok_push = 0
for p in find_shtetl_pods():
    base = pod_proxy_url(p.get("id") or "").rstrip("/")
    if not base:
        continue
    try:
        if _ensure_local_handler(base, on_status=None):
            ok_push += 1
    except Exception:
        pass

# Kick Pathé scrape if serve is up and job idle/error.
try:
    r = requests.get("http://127.0.0.1:8787/api/health", timeout=20)
    health = r.json() if r.ok else {}
except Exception as e:
    health = {"error": str(e)}

try:
    job = requests.get("http://127.0.0.1:8787/api/pathe/summary", timeout=10)
    summary = job.json() if job.ok else {}
except Exception:
    summary = {}

scrape = (summary.get("scrape") or summary.get("pathe_scrape") or {})
status = (scrape.get("status") if isinstance(scrape, dict) else None) or ""
if status in ("", "idle", "error", "done"):
    try:
        sr = requests.post(
            "http://127.0.0.1:8787/api/pathe/scrape",
            json={"max_videos": "all", "workers": want},
            timeout=30,
        )
        print(f"scrape_start {sr.status_code} {(sr.text or '')[:120]}", flush=True)
    except Exception as e:
        print(f"scrape_start_err {e}", flush=True)

out = {
    "ts": int(time.time()),
    "want": want,
    "active": count_active_shtetl_pods(),
    "ready_urls": len(bases or []),
    "pushed": ok_push,
    "ops_healthy": (health.get("summary") or {}).get("healthy_count"),
    "ops_pods": (health.get("summary") or {}).get("pod_count"),
    "ops_pool": (health.get("summary") or {}).get("scrape_pool_size"),
    "alerts": [a.get("code") for a in (health.get("alerts") or [])][:8],
}
print(json.dumps(out), flush=True)
print(
    f"active={out['active']}/{want} ops={out['ops_healthy']}/{out['ops_pods']} "
    f"pool={out['ops_pool']} pushed={ok_push}",
    flush=True,
)
