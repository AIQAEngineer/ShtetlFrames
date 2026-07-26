import sys
import time

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from runpod_client import get_pod_pool, set_pod_pool
from runpod_provision import ensure_pods, find_shtetl_pods, terminate_pod

print("listing…", flush=True)
t0 = time.time()
pods = find_shtetl_pods()
print(f"live={len(pods)} in {time.time()-t0:.1f}s", flush=True)
for p in pods:
    print(" ", p.get("name"), p.get("id"), p.get("desiredStatus"), flush=True)
    pid = p.get("id")
    if pid:
        try:
            terminate_pod(pid)
            print("  terminated", pid[:12], flush=True)
        except Exception as e:
            print("  terminate failed", e, flush=True)

set_pod_pool([])
print("ensuring 1 healthy pod…", flush=True)

def note(m: str) -> None:
    print(" ", (m or "")[:140], flush=True)

bases = ensure_pods(count=1, on_status=note, min_ready=1, extra_fill_sec=0)
set_pod_pool(bases or [])
print("pool", get_pod_pool(), flush=True)
