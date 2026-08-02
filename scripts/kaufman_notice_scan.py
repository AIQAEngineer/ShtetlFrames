"""Scan Emanu-El issues on CDNC for 'Kaufman' via Scrapfly ASP.

The CDNC search index is broken (2025-2026 outage), so locate notices by
pulling every page's OCR through the Veridian getSectionText AJAX endpoint.
"""
import html as html_mod
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output", "pathe_259561_photo_id", "newspapers")
os.makedirs(OUT_DIR, exist_ok=True)

ISSUES = {
    "JW19350524": "24 May 1935 travel notice",
    "JW19351220": "20 Dec 1935 Pictures of Palestine",
    "JW19351227": "27 Dec 1935 Palestinian moving pictures",
    "JW19360110": "10 Jan 1936 Bernard Jr motion pictures",
    "JW19360131": "31 Jan 1936 Hadassah notice",
    "JW19360214": "14 Feb 1936 Hillel notice",
}
MAX_PAGE = 48


def load_scrapfly_key() -> str:
    env_path = os.path.join(ROOT, ".env")
    raw = open(env_path, "rb").read()
    text = ""
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
        try:
            text = raw.decode(enc)
        except Exception:
            continue
        if "SCRAPFLY" in text:
            break
    for line in text.splitlines():
        m = re.match(r"\s*SCRAPFLY_API_KEY\s*=\s*(\S+)", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise RuntimeError("SCRAPFLY_API_KEY not found in .env")


KEY = load_scrapfly_key()


def scrapfly_text(url: str) -> str:
    params = {
        "key": KEY,
        "url": url,
        "asp": "true",
        "country": "us",
        "render_js": "false",
    }
    api = "https://api.scrapfly.io/scrape?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(api, headers={"User-Agent": "ShtetlFrames/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    result = data.get("result") or {}
    if not result.get("success"):
        raise RuntimeError(f"scrapfly failed: {result.get('error') or data.get('message')}")
    status = int(result.get("status_code") or 0)
    if status >= 400:
        raise RuntimeError(f"http_{status}")
    return result.get("content") or ""


def strip_html(content: str) -> str:
    txt = html_mod.unescape(html_mod.unescape(content))
    txt = re.sub(r"<script[\s\S]*?</script>", " ", txt)
    txt = re.sub(r"<style[\s\S]*?</style>", " ", txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", txt).strip()


def page_url(issue: str, p: int) -> str:
    return (
        "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=da&command=getSectionText"
        f"&d={issue}.2.{p}&srpos=&f=AJAX&e=-------en--20--1--txt-txIN--------"
    )


def fetch_page_text(issue: str, p: int) -> str:
    """OCR text of one page; raises RuntimeError('http_404') past issue end."""
    return strip_html(scrapfly_text(page_url(issue, p)))


def find_last_page(issue: str) -> int:
    lo, hi = 1, 99
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        try:
            fetch_page_text(issue, mid)
            lo = mid
        except RuntimeError as e:
            if "404" in str(e):
                hi = mid
            else:
                raise
    return lo


def scan_issue(issue: str, last_page: int) -> list[dict]:
    hits = []
    lock = threading.Lock()
    pages = range(1, last_page + 1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_page_text, issue, p): p for p in pages}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                text = fut.result()
            except Exception as e:
                print(f"{issue} p{p}: ERROR {e}", flush=True)
                continue
            low = text.lower()
            idx = -1
            for term in ("kaufman", "kaufmann", "koufman"):
                idx = low.find(term)
                if idx >= 0:
                    break
            if idx >= 0:
                ctx = text[max(0, idx - 600): idx + 900]
                with lock:
                    hits.append({"page": p, "context": ctx})
                print(f"{issue} p{p}: *** KAUFMAN HIT ***", flush=True)
    return sorted(hits, key=lambda h: h["page"])


def main() -> None:
    report = {}
    for issue, desc in ISSUES.items():
        try:
            last = find_last_page(issue)
        except Exception as e:
            print(f"{issue}: end-detection failed: {e}", flush=True)
            last = MAX_PAGE
        print(f"{issue}: {last} pages — scanning", flush=True)
        hits = scan_issue(issue, last)
        report[issue] = {"desc": desc, "last_page": last, "hits": hits}
        with open(os.path.join(OUT_DIR, "scan_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"== {issue} done: {len(hits)} hits ==", flush=True)
    print(json.dumps({k: [h["page"] for h in v["hits"]] for k, v in report.items()}, indent=2))


if __name__ == "__main__":
    sys.exit(main())
