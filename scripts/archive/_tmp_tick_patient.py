"""Patient fleet tick: fill to 8, adopt ready into pool, do NOT thrash-terminate."""
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
    _classify_pod,
    _ensure_local_handler,
    get_pod_pool,
    set_pod_pool,
)
from runpod_provision import (
    MAX_PARALLEL_PODS,
    count_active_shtetl_pods,
    ensure_pods,
    find_shtetl_pods,
    pod_proxy_url,
    set_pod_create_ceiling,
    shtetl_hard_cap,
)

load_env()
set_pod_create_ceiling(None)  # clear any temporary create ceiling
want = max(1, min(int(app_config.RUNPOD_MAX_INFLIGHT or 8), MAX_PARALLEL_PODS))


def st(msg: str) -> None:
    print(f"  {msg}"[:180], flush=True)


def main() -> int:
    active = count_active_shtetl_pods()
    print(
        f"patient start active={active} hard_cap={shtetl_hard_cap()} want={want}",
        flush=True,
    )
    # Soft ensure: create deficit only; wait for at least 1 ready.
    bases = ensure_pods(count=want, on_status=st, min_ready=1, extra_fill_sec=0)
    ready: list[str] = []
    for p in find_shtetl_pods():
        base = pod_proxy_url(p.get("id") or "").rstrip("/")
        if not base:
            continue
        kind = _classify_pod(base)
        print(f"  {kind} {p.get('name')}", flush=True)
        if kind in ("ready", "scan", "download", "idle", "queued", "warming"):
            ready.append(base)
    # Prefer ensure-ready URLs, then classified ready/warming.
    pool = list(dict.fromkeys((bases or []) + ready))
    if pool:
        set_pod_pool(pool[:want])
    pushed = 0
    for base in (get_pod_pool() or [])[:want]:
        try:
            if _ensure_local_handler(base, on_status=None):
                pushed += 1
        except Exception:
            pass

    # Push pool into the live serve process + reset jobs-per-pod to PATHE_STACK_MAX.
    try:
        sr = requests.post(
            "http://127.0.0.1:8787/api/runpod/pool/sync",
            json={"reset_stack": True},
            timeout=90,
        )
        print(f"serve_pool_sync {sr.status_code} {(sr.text or '')[:160]}", flush=True)
    except Exception as e:
        print(f"serve_pool_sync_err {e}", flush=True)

    try:
        health = requests.get("http://127.0.0.1:8787/api/health", timeout=20).json()
    except Exception as e:
        health = {"error": str(e)}
    try:
        summary = requests.get("http://127.0.0.1:8787/api/pathe/summary", timeout=10).json()
    except Exception:
        summary = {}
    scrape = summary.get("scrape") or summary.get("pathe_scrape") or {}
    status = (scrape.get("status") if isinstance(scrape, dict) else None) or ""
    if status in ("", "idle", "error", "done"):
        try:
            sr = requests.post(
                "http://127.0.0.1:8787/api/pathe/scrape",
                json={"max_videos": "all", "workers": want},
                timeout=30,
            )
            print(f"scrape_start {sr.status_code}", flush=True)
        except Exception as e:
            print(f"scrape_start_err {e}", flush=True)

    s = health.get("summary") or {}
    out = {
        "ts": int(time.time()),
        "want": want,
        "active": count_active_shtetl_pods(),
        "pool": len(get_pod_pool() or []),
        "ready_urls": len(bases or []),
        "pushed": pushed,
        "ops_healthy": s.get("healthy_count"),
        "ops_pods": s.get("pod_count"),
        "ops_pool": s.get("scrape_pool_size"),
    }
    print(json.dumps(out), flush=True)
    print(
        f"active={out['active']}/{want} ops={out['ops_healthy']}/{out['ops_pods']} "
        f"pool={out['ops_pool']} pushed={pushed}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
