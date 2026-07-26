import json
import sys
import time
import urllib.request

sys.path.insert(0, "src")


def get(url: str, timeout: float = 25) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


h1 = get("http://127.0.0.1:8787/api/health")
s1 = get("http://127.0.0.1:8787/api/pathe/summary")
c1 = int((s1.get("scrape") or {}).get("completed") or 0)
t0 = time.time()
print("SUMMARY", json.dumps(h1.get("summary"), indent=2))
print("ALERTS", h1.get("alerts"))
print("JOB", (h1.get("jobs") or {}).get("pathe_scrape"))
print("QUEUE", (h1.get("queue") or {}).get("pathe"))
print("POOL", h1.get("pool"))
print("---PODS---")
for p in h1.get("pods") or []:
    msg = (p.get("message") or "")[:60]
    print(
        f"{p.get('name')}: healthy={p.get('healthy')} phase={p.get('phase')} "
        f"inflight={p.get('inflight')}/{p.get('inflight_limit_pathe')} "
        f"busy={p.get('busy')} q={p.get('queue_id')} {msg}"
    )
print("---LIVE---")
for x in s1.get("live") or []:
    print(" ", (x.get("title") or "")[:42], "|", (x.get("detail") or "")[:90])

time.sleep(30)
s2 = get("http://127.0.0.1:8787/api/pathe/summary")
h2 = get("http://127.0.0.1:8787/api/health")
c2 = int((s2.get("scrape") or {}).get("completed") or 0)
dt = max(0.1, time.time() - t0)
rate = (c2 - c1) / dt * 60
print("---30s DELTA---")
print(f"completed {c1} -> {c2} (+{c2-c1}) rate={rate:.1f}/min")
print("queue", (h2.get("queue") or {}).get("pathe"))
print("summary", h2.get("summary"))
print("workers", (s2.get("scrape") or {}).get("workers"), "msg", (s2.get("scrape") or {}).get("message"))
