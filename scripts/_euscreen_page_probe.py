import re
import sys

import requests

url = "https://www.euscreen.eu/item.html?id=EUS_F665CD1BE6294477A3854352F04D6854"
r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 ShtetlFrames/1.0"})
print("status:", r.status_code, "len:", len(r.text))
html = r.text

# Any direct media URLs?
media = sorted(set(re.findall(r'https?://[^\s"\'<>]+?\.(?:mp4|m3u8|webm|ogv|mov)(?:\?[^\s"\'<>]*)?', html, re.I)))
print(f"direct media urls in page: {len(media)}")
for m in media[:10]:
    print("  ", m[:160])

# Video/source tags
for m in re.findall(r"<(?:video|source)[^>]+>", html, re.I)[:10]:
    print("TAG:", m[:200])

# data-* attributes that smell like media config
for m in sorted(set(re.findall(r'data-[a-z\-]*(?:video|media|src|file|stream)[a-z\-]*="[^"]{0,160}"', html, re.I)))[:12]:
    print("DATA:", m[:200])
