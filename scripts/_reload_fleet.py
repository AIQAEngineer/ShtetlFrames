"""POST /reload to every live pod so they pull the latest worker code."""

import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from runpod_provision import find_shtetl_pods

pods = find_shtetl_pods()
print(f"pods: {len(pods)}")
for p in pods:
    pid = p.get("id") or ""
    name = p.get("name") or ""
    url = f"https://{pid}-8000.proxy.runpod.net/reload"
    try:
        r = requests.post(url, timeout=30)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
        print(f"{name} {pid[:12]} -> {r.status_code} {str(body)[:220]}")
    except Exception as e:
        print(f"{name} {pid[:12]} -> ERR {str(e)[:160]}")
