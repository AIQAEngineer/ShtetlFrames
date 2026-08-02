"""Watch the RunPod scrape: throughput, oversize skips, stalls. Prints one line/min."""

import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "http://127.0.0.1:8787/api/jobs/scrape"
t0 = time.time()
last_done = -1
last_change = time.time()
stalls = 0

while True:
    try:
        with urllib.request.urlopen(URL, timeout=10) as r:
            j = json.load(r).get("job") or {}
    except Exception as e:
        print(f"t+{int((time.time()-t0)/60)}m API unreachable: {e}", flush=True)
        time.sleep(60)
        continue

    done = int(j.get("completed") or 0)
    hits = int(j.get("hits") or 0)
    msg = (j.get("message") or "")
    status = j.get("status")
    mins = (time.time() - t0) / 60.0
    rate = done / mins if mins > 0 else 0.0
    oversize = msg.lower().count("oversize")

    if done != last_done:
        last_done = done
        last_change = time.time()
        stalls = 0
    else:
        quiet_min = (time.time() - last_change) / 60.0
        if quiet_min >= 10 and status == "running":
            stalls += 1
            first = msg.split("\n")[0][:150]
            print(f"STALL {int(quiet_min)}m no progress · done={done} · {first}", flush=True)
            last_change = time.time()  # re-arm

    first = msg.split("\n")[0][:150]
    print(
        f"t+{int(mins)}m done={done} hits={hits} rate={rate:.1f}/min oversize_refs={oversize} [{status}] {first}",
        flush=True,
    )

    if status not in ("running", "queued"):
        print(f"SCRAPE ENDED status={status} done={done} hits={hits}", flush=True)
        break
    time.sleep(60)
