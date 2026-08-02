"""Push this checkout's worker files to all shtetl pods (hot reload, no recreate)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from runpod_client import reload_all_pod_workers  # noqa: E402

out = reload_all_pod_workers(on_status=lambda m: print(f"  {m}"))
print(f"ok={out.get('ok')} reloaded={out.get('reloaded')}/{out.get('pod_count')}")
for pod in out.get("pods") or []:
    name = pod.get("name") or pod.get("id")
    push_http = pod.get("push_http")
    body = pod.get("push_body") or {}
    pending = body.get("pending_soft_recycle") if isinstance(body, dict) else None
    changed = body.get("changed") if isinstance(body, dict) else None
    err = pod.get("error") or pod.get("push_error")
    print(f"  {name}: push_http={push_http} changed={changed} pending_recycle={pending} err={err}")
