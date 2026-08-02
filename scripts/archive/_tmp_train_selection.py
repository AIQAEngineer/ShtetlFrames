import json, sys
sys.path.insert(0, "src")
from clip_ft import train_linear_probe
from runpod_client import push_clip_probe_to_pods
from runpod_provision import find_shtetl_pods, pod_proxy_url
from config import load_env

def status(m):
    print(m, flush=True)

load_env()
result = train_linear_probe(on_status=status, device="cpu")
print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2, default=str))
if not result.get("ok"):
    raise SystemExit(1)
try:
    pods = [p for p in find_shtetl_pods() if (p.get("desiredStatus") or "").upper() == "RUNNING"]
    urls = [pod_proxy_url(p["id"]) for p in pods] or None
    push = push_clip_probe_to_pods(urls=urls, force=True, on_status=status)
    print("PUSH", push)
except Exception as e:
    print("PUSH_SKIP", e)
