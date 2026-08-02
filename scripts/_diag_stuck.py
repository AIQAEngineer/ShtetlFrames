"""Diagnose why Pathé completions stalled."""
from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "output" / "shtetlframes.db"
LOG = ROOT / "debug-30525a.log"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
now = time.time()

print("=== status counts ===")
for status, n in con.execute("SELECT status, COUNT(*) FROM queue_items GROUP BY status"):
    print(f"  {status}: {n}")

print("\n=== oldest scanning by created_at (20) ===")
for r in con.execute(
    """
    SELECT id, title, detail, created_at, error
    FROM queue_items WHERE status='scanning'
    ORDER BY created_at ASC LIMIT 20
    """
):
    age = "?"
    try:
        ts = float(r["created_at"])
        if ts > 1e12:
            ts /= 1000.0
        age = f"{(now - ts) / 60:.1f}m"
    except Exception:
        age = str(r["created_at"])[:19]
    print(
        f"  id={r['id']} created_age={age} detail={(r['detail'] or '')[:50]!r} "
        f"err={(r['error'] or '')[:40]!r} title={(r['title'] or '')[:40]!r}"
    )

print("\n=== last 8 done by id desc ===")
for r in con.execute(
    """
    SELECT id, title, detail, created_at
    FROM queue_items WHERE status='done'
    ORDER BY id DESC LIMIT 8
    """
):
    print(f"  id={r['id']} detail={(r['detail'] or '')[:40]!r} title={(r['title'] or '')[:45]!r}")

con.close()

print("\n=== log patterns (last ~2MB / last 8k lines) ===")
size = LOG.stat().st_size
with LOG.open("rb") as f:
    f.seek(max(0, size - 2_000_000))
    chunk = f.read().decode("utf-8", errors="replace")
lines = chunk.splitlines()[-8000:]
ctr: Counter[str] = Counter()
samples: dict[str, list[str]] = {
    "retry_soft": [],
    "timeout": [],
    "worker_died": [],
    "done": [],
}
for line in lines:
    try:
        o = json.loads(line)
    except Exception:
        continue
    msg = o.get("message") or ""
    data = o.get("data") or {}
    detail = str(data.get("detail") or data.get("error") or data.get("status") or "")
    blob = f"{msg} {json.dumps(data, default=str)}".lower()
    if msg == "submit_scan":
        ctr["submit_scan"] += 1
        att = data.get("attempt")
        if isinstance(att, int) and att >= 3:
            ctr["submit_attempt_ge3"] += 1
    if "retry_soft" in blob:
        ctr["retry_soft"] += 1
        if len(samples["retry_soft"]) < 4:
            samples["retry_soft"].append(detail[:140] or msg)
    if "pod_scan_timeout" in blob or "timeout" in detail.lower():
        ctr["timeout"] += 1
        if len(samples["timeout"]) < 4:
            samples["timeout"].append(detail[:140] or msg)
    if "worker_died" in blob:
        ctr["worker_died"] += 1
    if "http_524" in blob:
        ctr["http_524"] += 1
    if "http_503" in blob:
        ctr["http_503"] += 1
    if data.get("status") == "done":
        ctr["status_done"] += 1
        if len(samples["done"]) < 3:
            samples["done"].append(f"id={data.get('item_id')} {detail[:60]}")
    if "queued for a download" in blob or "prefetch" in blob:
        ctr["prefetch_signal"] += 1

print("counts:", dict(ctr))
for k, v in samples.items():
    if v:
        print(f"  sample {k}:")
        for s in v:
            print(f"    - {s}")

print("\n=== pod /health ===")
pods = [
    "mis60b95ted4b2",
    "b0ybwkjmt25g5x",
    "q7akco35i6idht",
    "00fzi44ynwiho4",
    "wravpkqt5oapmz",
    "opdzcrsd0hujvv",
    "zknbprp8mvwhlm",
    "8dwxykrtty9myk",
]
for pid in pods:
    try:
        h = requests.get(f"https://{pid}-8000.proxy.runpod.net/health", timeout=20).json()
        sync = h.get("github_sync") or {}
        prog = h.get("progress") or {}
        print(
            f"  {pid}: inflight={h.get('inflight')} lim={h.get('inflight_limit_pathe')} "
            f"phase={prog.get('phase')} pct={prog.get('pct')} q={prog.get('queue_id')} "
            f"msg={(prog.get('msg') or '')[:40]!r} "
            f"sync={list(sync.keys())[:6]}"
        )
    except Exception as e:
        print(f"  {pid}: ERR {type(e).__name__}: {e}")
