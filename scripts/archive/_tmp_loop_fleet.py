"""Audit fleet health for the agent loop. Exit 0 always; print summary JSON line."""
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
from db import get_job
from runpod_client import _classify_pod, get_pod_pool
from runpod_provision import (
    MAX_PARALLEL_PODS,
    find_shtetl_pods,
    pod_proxy_url,
    shtetl_account_cap,
)

load_env()
want = max(1, min(int(app_config.RUNPOD_MAX_INFLIGHT or 8), MAX_PARALLEL_PODS))
pods = find_shtetl_pods()
healthy = []
booting = []
dead = []
for p in pods:
    pid = p.get("id") or ""
    name = p.get("name") or pid[:12]
    base = pod_proxy_url(pid).rstrip("/")
    rt = p.get("runtime") if isinstance(p.get("runtime"), dict) else {}
    ports = (rt or {}).get("ports") or []
    try:
        uptime = float((rt or {}).get("uptimeInSeconds") or 0.0)
    except (TypeError, ValueError):
        uptime = 0.0
    kind = _classify_pod(base)
    entry = {
        "name": name,
        "kind": kind,
        "ports": len(ports),
        "uptime": uptime,
        "status": (p.get("desiredStatus") or ""),
    }
    if kind not in ("dead", "broken", "warming", "unknown"):
        healthy.append(entry)
    elif kind == "warming" or not ports or uptime < 180:
        # Young pods with ports often look "dead" via proxy 502 — count as booting.
        booting.append(entry)
    else:
        dead.append(entry)

job = get_job("pathe_scrape") or {}
summary = {
    "ts": int(time.time()),
    "want": want,
    "graphql": len(pods),
    "healthy": len(healthy),
    "booting": len(booting),
    "dead": len(dead),
    "pool": len(get_pod_pool()),
    "cap": shtetl_account_cap(),
    "scrape": job.get("status"),
    "msg": (job.get("message") or "")[:120],
    "ok": len(healthy) >= max(2, want // 2) and len(dead) == 0,
}
print(json.dumps(summary), flush=True)
print(
    f"healthy={summary['healthy']}/{summary['graphql']} "
    f"booting={summary['booting']} dead={summary['dead']} "
    f"want={want} scrape={summary['scrape']}",
    flush=True,
)
for d in dead[:8]:
    print(f"  DEAD {d['name']} kind={d['kind']} ports={d['ports']} up={d['uptime']:.0f}", flush=True)
