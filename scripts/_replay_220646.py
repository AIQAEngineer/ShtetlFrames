"""Fetch a real /result payload from a pod and replay the client-side still path locally."""
import base64
import json
import sys
import tempfile
from pathlib import Path

import requests

sys.path.insert(0, "src")
from still_store import _looks_like_image, save_candidate_still  # noqa: E402

B = "https://azrix90atg7n5b-8000.proxy.runpod.net"
r = requests.get(f"{B}/result", params={"queue_id": "220646"}, timeout=20)
data = r.json()
segs = data.get("segments") or []
print(f"segments: {len(segs)}  pending={data.get('pending')}  stills_on_disk={data.get('stills_on_disk')}")
out = {"segments": segs}

# Replay runpod_client._materialize_segment_stills exactly as the client runs it.
sys.path.insert(0, str(Path("src").resolve()))
import runpod_client  # noqa: E402

runpod_client._materialize_segment_stills(out)
for i, s in enumerate(out["segments"], 1):
    b64 = s.get("still_b64") or ""
    loc = s.get("_local_still")
    try:
        raw = base64.standard_b64decode(str(b64).encode("ascii"), validate=False)
        dec = f"{len(raw)}B magic={raw[:3].hex()} looks_img={_looks_like_image(raw)}"
    except Exception as e:
        dec = f"DECODE_ERR {e}"
        raw = b""
    print(f"seg{i}: b64_len={len(b64)} decode=[{dec}] _local_still={loc}")
    print(f"      notes={str(s.get('notes'))[:90]}")
    if raw and _looks_like_image(raw):
        dest = Path(tempfile.gettempdir()) / f"replay_220646_{i}.jpg"
        saved = save_candidate_still(999990 + i, b64=b64)
        print(f"      save_candidate_still(test id {999990+i}) -> {saved}")
