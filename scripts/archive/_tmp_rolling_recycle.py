"""Rolling recreate of all shtetl pods so they boot the stall-fix code from main.

One pod at a time: terminate at provider -> app maintain drops+creates replacement
-> wait until fleet healthy again -> next pod. Stops early on repeated failure.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests
from config import load_env
from runpod_client import drop_pod_url
from runpod_provision import find_shtetl_pods, pod_proxy_url

load_env()

HEALTH = "http://127.0.0.1:8787/api/health"
SYNC = "http://127.0.0.1:8787/api/runpod/pool/sync"
ROUND_TIMEOUT_S = 25 * 60


def healthy_count() -> tuple[int, int]:
    try:
        j = requests.get(HEALTH, timeout=30).json()
        s = j.get("summary") or {}
        return int(s.get("healthy_count") or 0), int(s.get("pod_count") or 0)
    except Exception:
        return -1, -1


def kick_maintain() -> None:
    try:
        requests.post(SYNC, json={}, timeout=120)
    except Exception as e:
        print(f"  sync kick err: {str(e)[:120]}", flush=True)


def main() -> int:
    pods = [(p.get("id"), p.get("name")) for p in find_shtetl_pods() if p.get("id")]
    print(f"rolling recycle of {len(pods)} pods", flush=True)
    fails = 0
    for i, (pid, name) in enumerate(pods, 1):
        base = pod_proxy_url(pid)
        hc, pc = healthy_count()
        print(f"[{i}/{len(pods)}] terminate {name} {pid[:12]} (fleet now {hc}/{pc})", flush=True)
        try:
            drop_pod_url(base, terminate=True, reason="stall_fix_recycle")
        except Exception as e:
            print(f"  terminate call err: {str(e)[:160]}", flush=True)
        time.sleep(20)  # let provider register the termination
        kick_maintain()
        t0 = time.time()
        last_log = 0.0
        while time.time() - t0 < ROUND_TIMEOUT_S:
            hc, pc = healthy_count()
            if hc >= len(pods):
                print(f"  fleet healthy again {hc}/{pc} after {int(time.time()-t0)}s", flush=True)
                break
            if time.time() - last_log > 60:
                print(f"  waiting… healthy {hc}/{pc} ({int(time.time()-t0)}s)", flush=True)
                last_log = time.time()
                kick_maintain()
            time.sleep(15)
        else:
            fails += 1
            print(f"  TIMEOUT waiting for fleet after {name}; fails={fails}", flush=True)
            if fails >= 2:
                print("ABORT: two rounds failed to recover — stopping.", flush=True)
                return 1
        time.sleep(30)
    hc, pc = healthy_count()
    print(f"DONE rolling recycle — fleet {hc}/{pc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
