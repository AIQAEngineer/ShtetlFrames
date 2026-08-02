"""Replace SSL/proxy-dead pods; refill pool; keep Pathé scrape running."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import requests
from config import load_env
import config as app_config
from runpod_client import _classify_pod, maintain_pod_pool, set_pod_pool, get_pod_pool
from runpod_provision import (
    MAX_PARALLEL_PODS, count_active_shtetl_pods, ensure_pods,
    find_shtetl_pods, pod_proxy_url, terminate_pod, set_pod_create_ceiling,
)

load_env()
set_pod_create_ceiling(None)
want = max(1, min(int(app_config.RUNPOD_MAX_INFLIGHT or 8), MAX_PARALLEL_PODS))
killed = 0
for p in find_shtetl_pods():
    pid = p.get("id") or ""
    name = p.get("name") or pid[:12]
    base = pod_proxy_url(pid).rstrip("/")
    if not base:
        continue
    status = (p.get("desiredStatus") or "").upper()
    if status in ("EXITED", "FAILED", "TERMINATED"):
        print(f"kill {name} status={status}", flush=True)
        try:
            terminate_pod(pid); killed += 1
        except Exception as e:
            print(f"  fail {e}"[:120], flush=True)
        continue
    # Hard SSL / connect failure on /health while claimed RUNNING
    dead_http = False
    try:
        r = requests.get(base + "/health", timeout=6)
        if r.status_code in (404, 502, 520, 521, 522, 523, 524) and status == "RUNNING":
            # only if uptime suggests not brand-new boot
            rt = p.get("runtime") if isinstance(p.get("runtime"), dict) else {}
            up = float((rt or {}).get("uptimeInSeconds") or 0)
            if up >= 180:
                dead_http = True
    except requests.RequestException as e:
        err = str(e).lower()
        if any(x in err for x in ("ssl", "eof", "connection", "timed out", "timeout")):
            rt = p.get("runtime") if isinstance(p.get("runtime"), dict) else {}
            up = float((rt or {}).get("uptimeInSeconds") or 0)
            # young boots get grace
            if up >= 120 or up == 0:
                # up==0 often means runtime missing while proxy dead
                dead_http = True
    if dead_http:
        print(f"kill {name} proxy_dead", flush=True)
        try:
            terminate_pod(pid); killed += 1
        except Exception as e:
            print(f"  fail {e}"[:120], flush=True)

print(f"killed={killed}", flush=True)
time.sleep(2)

def st(m): print(f"  {m}"[:160], flush=True)
bases = ensure_pods(count=want, on_status=st, min_ready=1, extra_fill_sec=0)
if bases:
    set_pod_pool(bases)
alive = maintain_pod_pool(target=want, on_status=st)
print(f"maintain alive={len(alive)} pool={len(get_pod_pool())}", flush=True)

# Push into live serve
try:
    r = requests.post("http://127.0.0.1:8787/api/runpod/pool/sync", json={"reset_stack": True, "target": want}, timeout=120)
    print(f"serve_sync {r.status_code} {(r.text or '')[:160]}", flush=True)
except Exception as e:
    print(f"serve_sync_err {e}", flush=True)

try:
    h = requests.get("http://127.0.0.1:8787/api/health", timeout=60).json()
except Exception as e:
    h = {"error": str(e)}
s = h.get("summary") or {}
out = {
    "ts": int(time.time()),
    "killed": killed,
    "active": count_active_shtetl_pods(),
    "want": want,
    "healthy": s.get("healthy_count"),
    "idle": s.get("idle_healthy_count"),
    "pool": s.get("scrape_pool_size"),
    "alerts": [a.get("code") for a in (h.get("alerts") or [])][:8],
}
print(json.dumps(out), flush=True)

# Ensure scrape running
try:
    summary = requests.get("http://127.0.0.1:8787/api/pathe/summary", timeout=15).json()
    scrape = summary.get("scrape") or {}
    if (scrape.get("status") or "") not in ("running",):
        requests.post("http://127.0.0.1:8787/api/pathe/scrape", json={"max_videos": "all", "workers": want}, timeout=30)
        print("scrape restarted", flush=True)
    else:
        print(f"scrape ok {(scrape.get('message') or '')[:100]}", flush=True)
except Exception as e:
    print(f"scrape_err {e}", flush=True)
