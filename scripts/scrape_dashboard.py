"""Live scrape dashboard — polls the local API and redraws a compact panel.

Visible companion to the web UI: header stats, a 5-minute rate history, and a
few live worker lines. History lines also append to output/dashboard_history.log
so the agent's loop can read rates without extra parsing.
"""

import json
import os
import re
import sys
import time
import urllib.request
from collections import deque

os.system("")  # enable ANSI colors on the Windows console
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8787/api/jobs/scrape"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST_LOG = os.path.join(ROOT, "output", "dashboard_history.log")
POLL_SEC = 15
HIST_EVERY_SEC = 300
BAR_W = 28
HIST_KEEP = 9

C = {
    "r": "\033[0m",
    "dim": "\033[90m",
    "cyan": "\033[96m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "bold": "\033[1m",
}


def fetch():
    try:
        with urllib.request.urlopen(API, timeout=10) as r:
            return json.load(r).get("job") or {}
    except Exception:
        return None


def fmt_eta(sec):
    if sec <= 0 or sec != sec or sec == float("inf"):
        return "—"
    h = sec / 3600.0
    if h >= 48:
        return f"{h / 24:.1f}d"
    if h >= 1:
        return f"{h:.1f}h"
    return f"{int(sec / 60)}m"


def bar(pct):
    fill = int(BAR_W * max(0.0, min(100.0, pct)) / 100.0)
    return "█" * fill + "░" * (BAR_W - fill)


def main():
    samples = deque()  # (mono, done)
    hist = deque(maxlen=HIST_KEEP)
    t0 = time.time()
    last_hist = t0 - HIST_EVERY_SEC + 60  # first history line ~1m in, then every 5m
    start_done = None

    while True:
        job = fetch()
        now = time.time()
        now_s = time.strftime("%H:%M:%S")

        if not job:
            print("\033[H\033[J", end="")
            print(f"{C['red']}API unreachable — is the server up?{C['r']}  {now_s}")
            time.sleep(POLL_SEC)
            continue

        done = int(job.get("completed") or 0)
        total = int(job.get("total") or 0)
        hits = int(job.get("hits") or 0)
        status = str(job.get("status") or "?")
        msg = job.get("message") or ""
        if start_done is None:
            start_done = done

        m = re.search(r"(\d+)\s*err", msg)
        err = int(m.group(1)) if m else 0
        m = re.search(r"(\d+)\s*active", msg)
        active = int(m.group(1)) if m else 0

        samples.append((now, done))
        while samples and now - samples[0][0] > 600:
            samples.popleft()

        def rate_over(sec):
            old = None
            for t, d in samples:
                if now - t >= sec:
                    old = (t, d)
                else:
                    break
            if not old or now - old[0] < sec * 0.5:
                return None
            return (done - old[1]) / ((now - old[0]) / 60.0)

        r5 = rate_over(300)
        r_all = (done - start_done) / ((now - t0) / 60.0) if now > t0 + 30 else None
        pct = (100.0 * done / total) if total else 0.0
        eta = fmt_eta((total - done) / (r5 / 60.0)) if r5 and r5 > 0 and total else "—"

        if now - last_hist >= HIST_EVERY_SEC:
            last_hist = now
            r5s = f"{r5:.1f}/min" if r5 is not None else "—"
            line = (
                f"{time.strftime('%H:%M')}  +{done - (samples[0][1] if samples else done):>4} since window"
                f"  {r5s:>9}  done {done:,}  hits {hits}  err {err}"
            )
            hist.append(line)
            try:
                with open(HIST_LOG, "a", encoding="utf-8") as f:
                    f.write(
                        f"{time.strftime('%Y-%m-%d %H:%M')} done={done} hits={hits} "
                        f"err={err} active={active} rate5m={r5s} status={status}\n"
                    )
            except OSError:
                pass

        workers = [ln for ln in msg.split("\n")[1:] if ln.strip()][:3]
        r5_txt = f"{r5:.1f}/min" if r5 is not None else "warming up…"
        rall_txt = f"{r_all:.1f}/min" if r_all is not None else "—"
        stat_col = C["green"] if status == "running" else C["yellow"]

        out = []
        out.append(f"{C['cyan']}╔══ ShtetlFrames — RunPod scrape ═══════════════════════════════╗{C['r']}")
        out.append(
            f"  {C['bold']}{done:,}{C['r']} / {total:,}  ({pct:.1f}%)  "
            f"{C['green']}{bar(pct)}{C['r']}"
        )
        out.append(
            f"  rate {C['green']}{r5_txt:>12}{C['r']} (5m)   session {rall_txt:>9}   "
            f"ETA {C['cyan']}{eta}{C['r']}"
        )
        out.append(
            f"  hits {C['yellow']}{hits}{C['r']}   errors {C['red']}{err}{C['r']}   "
            f"active {active}   status {stat_col}{status}{C['r']}"
        )
        if workers:
            out.append(f"{C['dim']}  ── right now ──────────────────────────────────────────{C['r']}")
            for w in workers:
                out.append(f"{C['dim']}  {w[:66]}{C['r']}")
        out.append(f"{C['cyan']}╠══ rate history (per-min, every 5m) ══════════════════════════╣{C['r']}")
        for h in hist:
            out.append(f"  {h}")
        out.append(f"{C['dim']}  updated {now_s} — log: output/dashboard_history.log{C['r']}")

        print("\033[H\033[J" + "\n".join(out), flush=True)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
