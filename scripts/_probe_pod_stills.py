"""Read-only probe: which handler generation runs on each pod, and does GET /still work?

Usage: .\.venv\Scripts\python.exe scripts\_probe_pod_stills.py
"""
import json

import requests

PODS = [
    "20c61y52r7ze6o",
    "i8wset2osgx42x",
    "vjphsg0gdaqkck",
    "azrix90atg7n5b",
    "p6zv1dv9rzq9on",
    "zm8r80d2a29yln",
    "ujbjbe5k5alhi6",
    "qz66rh02x3iy68",
]

# Recent queue ids seen in debug log (~6:44-6:53 PM today) — stills may still be on disk.
RECENT_QIDS = ["220597", "220646", "220647", "220644", "220645"]


def base(pid: str) -> str:
    return f"https://{pid}-8000.proxy.runpod.net"


def main() -> None:
    for pid in PODS:
        b = base(pid)
        print(f"\n=== {pid} ===")
        # 1) Handler generation probe: /still with a bogus queue id.
        try:
            r = requests.get(f"{b}/still", params={"queue_id": "__probe__", "index": 1}, timeout=15)
            body = r.text[:160].replace("\n", " ")
            print(f"  GET /still bogus  -> {r.status_code} {body}")
        except Exception as e:
            print(f"  GET /still bogus  -> ERR {type(e).__name__} {str(e)[:100]}")
        # 2) /result for a real recent job — inspect segment keys for still_b64/still_index.
        for qid in RECENT_QIDS:
            try:
                r = requests.get(f"{b}/result", params={"queue_id": qid}, timeout=15)
            except Exception as e:
                print(f"  GET /result {qid} -> ERR {type(e).__name__} {str(e)[:80]}")
                continue
            try:
                data = r.json()
            except Exception:
                print(f"  GET /result {qid} -> {r.status_code} non-json len={len(r.content)}")
                continue
            if not isinstance(data, dict):
                print(f"  GET /result {qid} -> {r.status_code} {str(data)[:80]}")
                continue
            if data.get("pending"):
                print(f"  GET /result {qid} -> pending phase={data.get('phase')}")
                continue
            segs = data.get("segments") or []
            if not segs:
                print(f"  GET /result {qid} -> done, 0 segments keys={sorted(data.keys())[:12]}")
                continue
            s0 = segs[0] if isinstance(segs[0], dict) else {}
            keys = sorted(s0.keys())
            has_b64 = [bool(s.get("still_b64")) for s in segs if isinstance(s, dict)]
            b64_lens = [len(str(s.get("still_b64") or "")) for s in segs if isinstance(s, dict)]
            print(f"  GET /result {qid} -> {len(segs)} segs, seg0_keys={keys}")
            print(f"      still_b64 present={has_b64} lens={b64_lens} stills_on_disk={data.get('stills_on_disk')}")
            # 3) If segments exist, try GET /still for index of seg0.
            idx = s0.get("still_index") or 1
            try:
                rs = requests.get(f"{b}/still", params={"queue_id": qid, "index": idx}, timeout=15)
                magic = rs.content[:3].hex() if rs.content else ""
                print(f"      GET /still qid={qid} idx={idx} -> {rs.status_code} len={len(rs.content)} magic={magic} ctype={rs.headers.get('content-type')}")
            except Exception as e:
                print(f"      GET /still qid={qid} idx={idx} -> ERR {type(e).__name__} {str(e)[:80]}")
            break  # one real job per pod is enough


if __name__ == "__main__":
    main()
