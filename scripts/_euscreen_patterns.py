import collections
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from config import DATA_DIR

pat = collections.Counter()
for line in (DATA_DIR / "europeana" / "resolve_media.jsonl").open(encoding="utf-8"):
    if not line.strip():
        continue
    u = json.loads(line)["url"]
    if "euscreen.eu" in u:
        path = urllib.parse.urlparse(u).path
        page = path.rsplit("/", 1)[-1].split("?")[0] or "(root)"
        pat[page] += 1
print("euscreen.eu page patterns:")
for p, c in pat.most_common(10):
    print(f"  {c:6d}  {p}")
