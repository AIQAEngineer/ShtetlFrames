"""One-shot pod fleet audit."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests
from config import load_env
import config as app_config
from db import get_job
from runpod_client import get_pod_pool, _classify_pod
from runpod_provision import (
    count_active_shtetl_pods,
    find_shtetl_pods,
    pod_create_ceiling,
    pod_creates_blocked,
    pod_proxy_url,
    shtetl_account_cap,
)

load_env()
print("MAX_INFLIGHT", getattr(app_config, "RUNPOD_MAX_INFLIGHT", None))
print("cap", shtetl_account_cap(), "active", count_active_shtetl_pods())
print("blocked", pod_creates_blocked(), "ceiling", pod_create_ceiling())
print("pool", len(get_pod_pool()))
for j in ("pathe_scrape", "pathe_discover"):
    job = get_job(j) or {}
    print(j, job.get("status"), (job.get("message") or "")[:100])
pods = find_shtetl_pods()
print("graphql", len(pods))
healthy = 0
for p in pods:
    pid = p.get("id") or ""
    base = pod_proxy_url(pid).rstrip("/")
    rt = p.get("runtime") if isinstance(p.get("runtime"), dict) else {}
    ports = (rt or {}).get("ports") or []
    up = (rt or {}).get("uptimeInSeconds")
    try:
        kind = _classify_pod(base)
    except Exception as e:
        kind = f"err:{e}"[:40]
    http = "?"
    try:
        r = requests.get(base + "/health", timeout=5)
        if r.status_code == 200 and r.content:
            d = r.json()
            http = f"200 ok={d.get('ok')} models={d.get('models_ready')} inflight={d.get('inflight')}"
            if d.get("ok") and d.get("models_ready"):
                healthy += 1
        else:
            http = str(r.status_code)
    except Exception as e:
        http = str(e)[:50]
    print(
        p.get("name"),
        pid[:12],
        (p.get("desiredStatus") or "?"),
        "ports",
        len(ports),
        "up",
        up,
        "class",
        kind,
        "http",
        http,
    )
print("healthy", healthy, "/", len(pods))
