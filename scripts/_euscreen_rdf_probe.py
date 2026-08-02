import re

import requests

VID = "EUS_F665CD1BE6294477A3854352F04D6854"
UA = {"User-Agent": "Mozilla/5.0 ShtetlFrames/1.0"}

rdf_url = f"http://lod.euscreen.eu/data/{VID}.rdf"
r = requests.get(rdf_url, timeout=30, headers=UA)
print("RDF status:", r.status_code, "len:", len(r.text))
media = sorted(set(re.findall(r'https?://[^\s"\'<>]+?\.(?:mp4|m3u8|webm|ogv|mov)(?:\?[^\s"\'<>]*)?', r.text, re.I)))
print(f"media urls in RDF: {len(media)}")
for m in media[:10]:
    print("  ", m[:180])

# Guess noterik video paths based on the image.jpg location
base = f"https://images3.noterik.com/domain/euscreenxl/user/eu_dr/video/{VID}"
for cand in (f"{base}/video.mp4", f"{base}/rawvideo.mp4", f"{base}/h264.mp4", f"{base}/1.mp4"):
    try:
        h = requests.head(cand, timeout=15, headers=UA, allow_redirects=True)
        print(h.status_code, h.headers.get("Content-Type", ""), h.headers.get("Content-Length", ""), cand)
    except Exception as e:
        print("ERR", cand, str(e)[:80])
