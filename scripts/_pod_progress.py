import json
import time

import requests

PODS = [
    "mis60b95ted4b2",
    "b0ybwkjmt25g5x",
    "q7akco35i6idht",
    "00fzi44ynwiho4",
    "wravpkqt5oapmz",
    "opdzcrsd0hujvv",
    "zknbprp8mvwhlm",
    "8dwxykrtty9myk",
]

now = time.time()
for pid in PODS:
    url = f"https://{pid}-8000.proxy.runpod.net/progress"
    try:
        r = requests.get(url, timeout=25)
        data = r.json()
    except Exception as e:
        print(f"{pid}: ERR {type(e).__name__} {e}")
        continue
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if jobs is None:
        jobs = data if isinstance(data, list) else [data]
    print(f"{pid}: {len(jobs)} job(s)")
    for j in jobs:
        if not isinstance(j, dict):
            print(f"   raw: {str(j)[:200]}")
            continue
        qid = j.get("queue_id") or j.get("qid")
        phase = j.get("phase") or j.get("status") or "?"
        started = j.get("started_at") or j.get("t0") or j.get("start_ts")
        age = f"{(now - float(started)) / 60:.1f}m" if started else "?"
        dl = j.get("downloaded_bytes") or j.get("downloaded") or 0
        speed = j.get("speed") or j.get("bps") or 0
        pct = j.get("percent") or j.get("pct")
        msg = j.get("msg") or j.get("message") or ""
        try:
            dl_mb = float(dl) / 1e6
        except Exception:
            dl_mb = 0
        try:
            sp_mb = float(speed) / 1e6
        except Exception:
            sp_mb = 0
        print(
            f"   q{qid} {phase} age={age} dl={dl_mb:.1f}MB speed={sp_mb:.2f}MB/s pct={pct} msg={str(msg)[:80]}"
        )
