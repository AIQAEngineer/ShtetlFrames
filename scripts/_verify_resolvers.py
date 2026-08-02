import json
import os
import sys
from pathlib import Path

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from provider_resolvers import resolve_media_url

JSONL = Path(ROOT) / "data" / "europeana" / "resolve_media.jsonl"

euscreen, iwm = [], []
with JSONL.open("r", encoding="utf-8") as f:
    for line in f:
        if len(euscreen) >= 3 and len(iwm) >= 2:
            break
        try:
            rec = json.loads(line)
        except Exception:
            continue
        u = rec.get("url", "")
        if "euscreen.eu" in u and "item.html" in u and len(euscreen) < 3:
            euscreen.append(u)
        elif "iwm.org.uk" in u and "/collections/item/" in u and len(iwm) < 2:
            iwm.append(u)

print(f"samples: {len(euscreen)} euscreen, {len(iwm)} iwm\n")
ok = fail = 0
for u in euscreen + iwm:
    host = "euscreen" if "euscreen" in u else "iwm"
    resolved = resolve_media_url(u)
    if not resolved:
        print(f"FAIL resolve [{host}] {u}")
        fail += 1
        continue
    try:
        r = requests.head(resolved, timeout=30, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        code = r.status_code
        size = r.headers.get("Content-Length", "?")
    except Exception as e:
        code, size = f"err {e}", "?"
    status = "OK " if code == 200 else "FAIL"
    if code == 200:
        ok += 1
    else:
        fail += 1
    print(f"{status} [{host}] HTTP {code} bytes={size}\n      page:  {u}\n      media: {resolved[:150]}")

print(f"\nsuccess: {ok}/{ok + fail}")
