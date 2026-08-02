"""Fast Scrapfly capture: render page, dump canvas JPEG into DOM, scrape it."""
import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaufman_notice_scan import KEY, OUT_DIR, scrapfly_text, strip_html

TARGETS = [
    ("JW19350524", 15, "1935-05-24_travel_notice"),
    ("JW19351220", 14, "1935-12-20_pictures_of_palestine"),
    ("JW19351227", 36, "1935-12-27_lav_tovians_moving_pictures"),
    ("JW19360110", 55, "1936-01-10_pathfinders_bernard_jr"),
    ("JW19360131", 9, "1936-01-31_town_talk_palestine_screen"),
    ("JW19360214", 84, "1936-02-14_hillel_palestinian_experiences"),
]

# Dump canvas to a DOM node Scrapfly returns in HTML.
JS = """
(() => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  return (async () => {
    for (let i = 0; i < 40; i++) {
      const c = document.querySelector('canvas');
      if (c && c.width > 200 && c.height > 200) {
        // sample a few pixels — wait until not pure black
        const ctx = c.getContext('2d');
        let nonBlack = 0;
        try {
          const d = ctx.getImageData(10, 10, 40, 40).data;
          for (let j = 0; j < d.length; j += 16) {
            if (d[j] + d[j+1] + d[j+2] > 30) nonBlack++;
          }
        } catch (e) {}
        if (nonBlack > 5 || i > 25) {
          const jpg = c.toDataURL('image/jpeg', 0.9);
          let el = document.getElementById('__cap');
          if (!el) { el = document.createElement('pre'); el.id = '__cap'; document.body.appendChild(el); }
          el.textContent = jpg;
          return true;
        }
      }
      await sleep(500);
    }
    return false;
  })();
})()
"""


def scrape_capture(issue: str, page: int, name: str) -> dict:
    url = f"https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d={issue}.2.{page}"
    scenario = [
        {"wait": 4000},
        {"execute": {"script": JS}},
        {"wait": 2000},
    ]
    params = {
        "key": KEY,
        "url": url,
        "asp": "true",
        "country": "us",
        "render_js": "true",
        "rendering_wait": "5000",
        "js_scenario": json.dumps(scenario),
    }
    api = "https://api.scrapfly.io/scrape?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(api, headers={"User-Agent": "ShtetlFrames/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    result = data.get("result") or {}
    out = {"issue": issue, "page": page, "name": name, "success": result.get("success")}
    if not result.get("success"):
        out["error"] = result.get("error") or data.get("message")
        return out
    html = result.get("content") or ""
    m = re.search(r'id="__cap"[^>]*>(data:image/jpeg;base64,[^<]+)', html)
    if not m:
        m = re.search(r"(data:image/jpeg;base64,[A-Za-z0-9+/=]{1000,})", html)
    if not m:
        out["error"] = "no_canvas_data"
        out["html_len"] = len(html)
        # still save OCR text
        text_url = (
            "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=da&command=getSectionText"
            f"&d={issue}.2.{page}&srpos=&f=AJAX&e=-------en--20--1--txt-txIN--------"
        )
        try:
            ocr = strip_html(scrapfly_text(text_url))
            tpath = os.path.join(OUT_DIR, f"{name}.txt")
            open(tpath, "w", encoding="utf-8").write(ocr)
            out["ocr"] = tpath
        except Exception as e:
            out["ocr_err"] = str(e)
        return out
    b64 = m.group(1).split(",", 1)[1]
    jpg = base64.b64decode(b64)
    path = os.path.join(OUT_DIR, f"{name}.jpg")
    open(path, "wb").write(jpg)
    out["image"] = path
    out["bytes"] = len(jpg)
    # OCR sidecar
    text_url = (
        "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=da&command=getSectionText"
        f"&d={issue}.2.{page}&srpos=&f=AJAX&e=-------en--20--1--txt-txIN--------"
    )
    try:
        ocr = strip_html(scrapfly_text(text_url))
        tpath = os.path.join(OUT_DIR, f"{name}.txt")
        open(tpath, "w", encoding="utf-8").write(ocr)
        out["ocr"] = tpath
    except Exception as e:
        out["ocr_err"] = str(e)
    return out


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    # 2 parallel — Scrapfly ASP budget
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {pool.submit(scrape_capture, i, p, n): n for i, p, n in TARGETS}
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:
                r = {"name": futs[fut], "error": str(e)}
            print(json.dumps({k: v for k, v in r.items() if k != "html"}), flush=True)
            results.append(r)
    with open(os.path.join(OUT_DIR, "capture_log.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    # write index of confirmed notices from OCR already known
    print("DONE", sum(1 for r in results if r.get("image")), "images")


if __name__ == "__main__":
    sys.exit(main())
