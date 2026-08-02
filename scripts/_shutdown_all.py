"""One-off: terminate all shtetlframes RunPod pods (full shutdown)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import load_env  # noqa: E402

load_env()

from runpod_provision import find_shtetl_pods, terminate_shtetl_pods  # noqa: E402

before = find_shtetl_pods()
print(f"pods before: {len(before)}")
res = terminate_shtetl_pods()
print(f"terminate result: {res}")
after = find_shtetl_pods()
print(f"pods after: {len(after)}")
