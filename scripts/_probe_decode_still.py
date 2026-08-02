"""Fetch any currently-stored /result on the pod fleet and DECODE still_b64 like the client does."""
import base64
import sqlite3

import requests

PODS = [
    "20c61y52r7ze6o", "i8wset2osgx42x", "vjphsg0gdaqkck", "azrix90atg7n5b",
    "p6zv1dv9rzq9on", "zm8r80d2a29yln", "ujbjbe5k5alhi6", "qz66rh02x3iy68",
]

con = sqlite3.connect("output/shtetlframes.db")
qids = [
    str(r[0])
    for r in con.execute(
        "SELECT id FROM queue_items WHERE status='scanning' ORDER BY id DESC LIMIT 25"
    )
]
print("scanning qids:", qids)

found = 0
for pid in PODS:
    b = f"https://{pid}-8000.proxy.runpod.net"
    for qid in qids:
        try:
            r = requests.get(f"{b}/result", params={"queue_id": qid}, timeout=12)
            data = r.json()
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("pending", True):
            continue
        segs = data.get("segments") or []
        if not segs:
            continue
        found += 1
        print(f"\nFOUND pod={pid} qid={qid} segs={len(segs)} stills_on_disk={data.get('stills_on_disk')}")
        for i, s in enumerate(segs[:4], 1):
            b64 = s.get("still_b64") or s.get("image_b64") or ""
            print(f"  seg{i}: keys={sorted(s.keys())}")
            print(f"        b64 len={len(b64)} head={b64[:40]!r} tail={b64[-20:]!r}")
            try:
                raw = base64.standard_b64decode(str(b64).encode("ascii"), validate=False)
                print(f"        standard decode OK: {len(raw)}B magic={raw[:4].hex()}")
            except Exception as e:
                print(f"        standard decode FAIL: {e}")
                try:
                    raw = base64.urlsafe_b64decode(str(b64).encode("ascii"))
                    print(f"        urlsafe decode OK: {len(raw)}B magic={raw[:4].hex()}")
                except Exception as e2:
                    print(f"        urlsafe decode FAIL: {e2}")
        if found >= 3:
            raise SystemExit
