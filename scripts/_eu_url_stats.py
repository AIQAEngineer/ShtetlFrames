import collections
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from config import DATA_DIR
from download import is_direct_video_url, _should_use_ytdlp

path = DATA_DIR / "europeana" / "resolve_media.jsonl"
urls = []
for line in path.open(encoding="utf-8"):
    if line.strip():
        urls.append(json.loads(line)["url"])

n = len(urls)
direct = sum(1 for u in urls if is_direct_video_url(u))
ytdlp = sum(1 for u in urls if not is_direct_video_url(u) and _should_use_ytdlp(u))
other = n - direct - ytdlp
hosts = collections.Counter(urllib.parse.urlparse(u).netloc for u in urls)
print(f"resolved: {n}")
print(f"  direct video file: {direct}")
print(f"  yt-dlp handled host: {ytdlp}")
print(f"  other/unhandled host: {other}")
print("top hosts:")
for h, c in hosts.most_common(15):
    print(f"  {c:6d}  {h}")
