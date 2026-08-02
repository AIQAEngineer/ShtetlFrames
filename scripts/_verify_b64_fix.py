"""Validate the b64decode fix against a real pod /result payload (no DB writes)."""
import sys

import requests

sys.path.insert(0, "src")
from still_store import save_candidate_still, candidate_still_path  # noqa: E402

TRY = [
    ("20c61y52r7ze6o", "220633"),
    ("i8wset2osgx42x", "220650"),
    ("p6zv1dv9rzq9on", "220648"),
]

saved_any = False
for pid, qid in TRY:
    b = f"https://{pid}-8000.proxy.runpod.net"
    try:
        data = requests.get(f"{b}/result", params={"queue_id": qid}, timeout=15).json()
    except Exception as e:
        print(f"{pid}/{qid}: fetch err {e}")
        continue
    segs = data.get("segments") or []
    if not segs:
        print(f"{pid}/{qid}: no segments (expired?)")
        continue
    b64 = segs[0].get("still_b64") or ""
    dest = save_candidate_still(999991, b64=b64)
    print(f"{pid}/{qid}: b64 len={len(b64)} -> save_candidate_still -> {dest}")
    if dest:
        p = candidate_still_path(999991)
        print(f"   OK: {p.name} {p.stat().st_size} bytes, magic={p.read_bytes()[:3].hex()}")
        p.unlink()
        saved_any = True
        break

# Sanity: the old call form really does raise TypeError on this interpreter.
import base64  # noqa: E402

try:
    base64.standard_b64decode(b"AAAA", validate=False)
    print("old form: unexpectedly OK")
except TypeError as e:
    print(f"old form confirmed broken on this Python: {e}")
print("RESULT:", "PASS" if saved_any else "FAIL")
