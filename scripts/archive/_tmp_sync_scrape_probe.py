"""Sync pool to 8, resume Pathé scrape, force-push CLIP probe."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests
from config import load_env
from runpod_client import (
    _classify_pod,
    get_pod_pool,
    push_clip_probe_to_pods,
    set_pod_pool,
)
from runpod_provision import count_active_shtetl_pods, find_shtetl_pods, pod_proxy_url

load_env()

ready: list[str] = []
for p in find_shtetl_pods():
    base = pod_proxy_url(p.get("id") or "").rstrip("/")
    if not base:
        continue
    kind = _classify_pod(base)
    print(f"classify {p.get('name')} {kind}", flush=True)
    if kind in ("ready", "scan", "download", "idle", "queued", "warming"):
        ready.append(base)
if ready:
    set_pod_pool(ready[:8])
print(f"local_pool {len(get_pod_pool() or [])}", flush=True)

sr = requests.post(
    "http://127.0.0.1:8787/api/runpod/pool/sync",
    json={"reset_stack": True, "target": 8},
    timeout=120,
)
print(f"pool_sync {sr.status_code} {(sr.text or '')[:300]}", flush=True)

summary = requests.get("http://127.0.0.1:8787/api/pathe/summary", timeout=20).json()
scrape = summary.get("scrape") or summary.get("pathe_scrape") or {}
status = (scrape.get("status") if isinstance(scrape, dict) else None) or ""
msg = (scrape.get("message") or "")[:120] if isinstance(scrape, dict) else ""
print(f"scrape_before {status} {msg}", flush=True)
if status not in ("running",):
    r = requests.post(
        "http://127.0.0.1:8787/api/pathe/scrape",
        json={"max_videos": "all", "workers": 8},
        timeout=30,
    )
    print(f"scrape_start {r.status_code} {(r.text or '')[:200]}", flush=True)
else:
    print("scrape already running", flush=True)

print("pushing probe force=True...", flush=True)
push = push_clip_probe_to_pods(
    force=True, on_status=lambda m: print(f"  {m}"[:160], flush=True)
)
print(
    "PUSH",
    json.dumps(
        {
            "ok": push.get("ok"),
            "pushed": push.get("pushed"),
            "skipped": push.get("skipped"),
            "error": push.get("error"),
        }
    ),
    flush=True,
)
failed = 0
for row in push.get("results") or []:
    body = row.get("body") if isinstance(row.get("body"), dict) else {}
    if row.get("skipped"):
        tag = "skip"
    elif body.get("ok"):
        tag = "ok"
    else:
        tag = "fail"
        failed += 1
    err = (row.get("error") or "")[:80]
    print(
        f"  {tag} {row.get('name')} http={row.get('http')} via={row.get('via')} err={err}",
        flush=True,
    )
print(
    f"failed_count {failed} pushed {push.get('pushed')} skipped {push.get('skipped')}",
    flush=True,
)

h = requests.get("http://127.0.0.1:8787/api/health", timeout=60).json()
s = h.get("summary") or {}
summary2 = requests.get("http://127.0.0.1:8787/api/pathe/summary", timeout=20).json()
scrape2 = summary2.get("scrape") or {}
jobs = h.get("jobs") or {}
ps = jobs.get("pathe_scrape") or {}
out = {
    "serve_ok": h.get("ok"),
    "healthy": s.get("healthy_count"),
    "pod_count": s.get("pod_count"),
    "pool": s.get("scrape_pool_size"),
    "active_pods": count_active_shtetl_pods(),
    "scrape_status": ps.get("status") or scrape2.get("status"),
    "scrape_msg": ((ps.get("message") or scrape2.get("message") or "")[:140]),
    "probe_pushed": push.get("pushed"),
    "probe_skipped": push.get("skipped"),
    "probe_failed": failed,
    "probe_ok": push.get("ok"),
}
print("REPORT", json.dumps(out), flush=True)
