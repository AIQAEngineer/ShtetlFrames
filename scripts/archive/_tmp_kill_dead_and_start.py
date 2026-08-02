"""Kill obvious dead pods, then start Pathé scrape (soft-starts fleet)."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env
from runpod_client import _classify_pod
from runpod_provision import find_shtetl_pods, pod_proxy_url, terminate_pod

load_env()
for p in find_shtetl_pods():
    pid = p.get("id")
    if not pid:
        continue
    name = p.get("name") or pid[:12]
    rt = p.get("runtime") if isinstance(p.get("runtime"), dict) else {}
    ports = (rt or {}).get("ports") or []
    try:
        uptime = float((rt or {}).get("uptimeInSeconds") or 0.0)
    except (TypeError, ValueError):
        uptime = 0.0
    base = pod_proxy_url(pid).rstrip("/")
    kind = _classify_pod(base)
    status = (p.get("desiredStatus") or "").upper()
    kill = False
    reason = ""
    if status in ("EXITED", "FAILED", "TERMINATED"):
        kill, reason = True, status
    elif ports and kind in ("dead", "broken") and uptime >= 120:
        kill, reason = True, f"{kind}+ports up={uptime:.0f}"
    if kill:
        print(f"terminate {name} ({reason})", flush=True)
        try:
            terminate_pod(pid)
        except Exception as e:
            print(f"  fail: {e}"[:160], flush=True)

req = urllib.request.Request(
    "http://127.0.0.1:8787/api/pathe/scrape",
    data=json.dumps({"workers": 8, "max_videos": "all"}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    body = resp.read().decode("utf-8", errors="replace")
print("scrape_start", body[:300], flush=True)
