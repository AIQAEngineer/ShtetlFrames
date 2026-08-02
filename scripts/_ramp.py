"""Ramp helper: fleet snapshot + live settings for the Pathé throughput loop."""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DB = ROOT / "output" / "shtetlframes.db"
PATHE = "url LIKE '%britishpathe.com%'"


def snapshot() -> dict:
    out = {"ts": time.strftime("%H:%M:%S")}
    conn = sqlite3.connect(str(DB), timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        out["queue"] = {
            r["status"]: r["n"]
            for r in conn.execute(
                f"SELECT status, COUNT(*) n FROM queue_items WHERE {PATHE} GROUP BY status"
            )
        }
        out["settings"] = {
            r["key"]: r["value"]
            for r in conn.execute(
                "SELECT key, value FROM app_settings WHERE key IN "
                "('PATHE_STACK_MAX','RUNPOD_MAX_INFLIGHT')"
            )
        }
    finally:
        conn.close()

    # Pod fleet: phases via each pod's /health (aggregate progress included).
    try:
        import requests
        from config import load_env  # noqa: F401  (loads .env for API key)
        from runpod_provision import find_shtetl_pods, pod_proxy_url

        pods = []
        for p in find_shtetl_pods():
            pid = p.get("id") or ""
            if not pid:
                continue
            base = pod_proxy_url(pid).rstrip("/")
            row = {"id": pid[:14], "status": p.get("desiredStatus")}
            try:
                r = requests.get(f"{base}/health", timeout=20)
                if r.status_code == 200:
                    j = r.json()
                    prog = j.get("progress") or {}
                    row["phase"] = prog.get("phase")
                    row["msg"] = (prog.get("message") or "")[:40]
                    row["busy"] = j.get("busy") or j.get("inflight")
                    row["ready"] = j.get("models_ready")
                else:
                    row["phase"] = f"http_{r.status_code}"
            except Exception as e:
                row["phase"] = f"err:{str(e)[:40]}"
            pods.append(row)
        out["pods"] = pods
    except Exception as e:
        out["pods_error"] = str(e)[:200]
    return out


def set_setting(key: str, value: str) -> None:
    conn = sqlite3.connect(str(DB), timeout=20)
    try:
        conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "--set":
        set_setting(args[1], args[2])
        print(f"{args[1]} -> {args[2]}")
    snap = snapshot()
    print(json.dumps(snap, indent=2))
