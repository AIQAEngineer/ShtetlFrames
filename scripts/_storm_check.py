import json
import time
from collections import Counter
from pathlib import Path

log = Path(__file__).resolve().parents[1] / "debug-30525a.log"
now_ms = int(time.time() * 1000)
window_ms = 8 * 60 * 1000  # since last tick

kinds = Counter()
submits = 0
with log.open("r", encoding="utf-8", errors="replace") as fh:
    for line in fh:
        if '"timestamp"' not in line:
            continue
        try:
            ts = int(line.rsplit('"timestamp":', 1)[1].split("}")[0].strip().rstrip(","))
        except Exception:
            continue
        if now_ms - ts > window_ms:
            continue
        if "pod_scan_http" in line:
            kinds["pod_scan_http"] += 1
        elif "http_524" in line:
            kinds["http_524"] += 1
        elif "http_503" in line:
            kinds["http_503"] += 1
        elif "http_404" in line:
            kinds["http_404"] += 1
        elif "http_502" in line:
            kinds["http_502"] += 1
        elif '"message": "submit_scan"' in line:
            submits += 1

print(f"window: last {window_ms // 60000} min")
print(f"submit_scan attempts: {submits}")
for k, v in kinds.most_common():
    print(f"{k}: {v}")
if not kinds:
    print("no infra errors in window")
