"""One-off: force-push this checkout's worker files to all live pods via /sync_push.

The running scrape process caches push failures forever (_handler_pushed), so pods
recreated mid-run never received the current handler. This bypasses that cache.
"""

import sys

sys.path.insert(0, "src")

import requests  # noqa: E402

from runpod_client import _local_worker_files_for_push  # noqa: E402


def main() -> int:
    health = requests.get("http://127.0.0.1:8787/api/health", timeout=15).json()
    urls = (health.get("pool") or {}).get("urls") or []
    if not urls:
        print("no pod urls in /api/health pool")
        return 1
    files = _local_worker_files_for_push()
    print(f"pushing {len(files)} files to {len(urls)} pods: {sorted(files)}")
    ok_n = 0
    for raw in urls:
        base = raw if raw.startswith("http") else f"https://{raw}"
        base = base.rstrip("/")
        try:
            r = requests.post(f"{base}/sync_push", json={"files": files}, timeout=120)
            try:
                body = r.json()
            except Exception:
                body = {"raw": (r.text or "")[:160]}
            good = r.status_code == 200 and isinstance(body, dict) and body.get("ok")
            ok_n += 1 if good else 0
            print(f"{'OK ' if good else 'FAIL'} {base} -> {r.status_code} {str(body)[:200]}")
        except Exception as e:
            print(f"ERR  {base} -> {e}")
    print(f"done: {ok_n}/{len(urls)} pods updated")
    return 0 if ok_n == len(urls) else 2


if __name__ == "__main__":
    raise SystemExit(main())
