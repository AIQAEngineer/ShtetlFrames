import json
import time
import urllib.request

deadline = time.time() + 30 * 60
last = ""
while time.time() < deadline:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/api/train/summary", timeout=20) as r:
            t = json.loads(r.read().decode())
        s = t.get("seed") or {}
        yt = t.get("youtube_stats") or {}
        msg = str(s.get("message") or "")[:120]
        line = (
            f"{time.strftime('%H:%M:%S')} status={s.get('status')} phase={s.get('phase')} "
            f"prog={s.get('progress')} hits={s.get('hits')} yt={yt.get('n_total')} msg={msg}"
        )
        if line != last:
            print(line, flush=True)
            last = line
        if s.get("status") in ("done", "error"):
            print("FINAL", json.dumps({"seed": s, "youtube_stats": yt})[:1200], flush=True)
            break
    except Exception as e:
        print("poll_err", e, flush=True)
    time.sleep(15)
else:
    print("TIMEOUT", flush=True)
