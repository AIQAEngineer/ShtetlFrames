"""Capture CDNC newspaper page viewers via Scrapfly screenshots (ASP + render_js).

Saves PNG of the #viewer element (OpenSeadragon newspaper image) plus a
fullpage shot for context, per target page.
"""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaufman_notice_scan import KEY, OUT_DIR

TARGETS = [
    ("JW19350524", 15, "1935-05-24_travel_notice_p15"),
    ("JW19351220", 14, "1935-12-20_pictures_of_palestine_p14"),
]


def capture(issue: str, page: int, name: str) -> dict:
    url = f"https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d={issue}.2.{page}"
    params = {
        "key": KEY,
        "url": url,
        "asp": "true",
        "country": "us",
        "render_js": "true",
        "rendering_wait": "9000",
        "screenshots[viewer]": "#viewer",
        "screenshots[full]": "fullpage",
    }
    api = "https://api.scrapfly.io/scrape?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(api, headers={"User-Agent": "ShtetlFrames/1.0"})
    with urllib.request.urlopen(req, timeout=240) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    result = data.get("result") or {}
    out = {"issue": issue, "page": page, "name": name, "success": result.get("success")}
    if not result.get("success"):
        out["error"] = result.get("error") or data.get("message")
        return out
    shots = result.get("screenshots") or {}
    for tag, meta in shots.items():
        b64 = (meta or {}).get("image") or ""
        if not b64:
            out[f"{tag}_missing"] = True
            continue
        png = base64.b64decode(b64)
        path = os.path.join(OUT_DIR, f"{name}_{tag}.png")
        with open(path, "wb") as f:
            f.write(png)
        out[f"{tag}_file"] = path
        out[f"{tag}_bytes"] = len(png)
    return out


def main() -> None:
    targets = TARGETS
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        targets = json.load(open(os.path.join(OUT_DIR, "capture_targets.json"), encoding="utf-8"))
        targets = [(t["issue"], t["page"], t["name"]) for t in targets]
    results = []
    for issue, page, name in targets:
        try:
            r = capture(issue, page, name)
        except Exception as e:
            r = {"issue": issue, "page": page, "name": name, "error": str(e)}
        print(json.dumps(r), flush=True)
        results.append(r)
        time.sleep(2)
    with open(os.path.join(OUT_DIR, "capture_log.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
