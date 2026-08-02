"""Cleanup pass: re-fetch pages that 422'd/timed out in the first scan,
and determine true page counts where end-detection failed. Sequential,
with retries and backoff, to stay under Scrapfly rate limits."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaufman_notice_scan import OUT_DIR, fetch_page_text, find_last_page

REPORT_PATH = os.path.join(OUT_DIR, "scan_report.json")

ERRORED = {
    "JW19350524": [41, 57],
    "JW19351220": [18, 19, 20, 22, 27, 33, 38, 42, 46],
    "JW19351227": [10, 25, 31, 36, 56],
    "JW19360110": [8, 10, 17, 21, 24, 27, 35, 42, 44],
    "JW19360131": [12, 16, 22, 23, 29, 30, 31, 37, 48],
    "JW19360214": [24, 29, 32, 34, 45, 54, 57, 72, 75, 90],
}
END_UNKNOWN = {"JW19351220", "JW19360110", "JW19360131"}


def fetch_with_retry(issue: str, p: int, attempts: int = 5) -> str:
    delay = 6.0
    for i in range(attempts):
        try:
            return fetch_page_text(issue, p)
        except Exception as e:
            if i == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 1.6, 30.0)
    raise RuntimeError("unreachable")


def main() -> None:
    report = json.load(open(REPORT_PATH, encoding="utf-8"))
    for issue in ["JW19350524", "JW19351220", "JW19351227", "JW19360110", "JW19360131", "JW19360214"]:
        entry = report[issue]
        if issue in END_UNKNOWN:
            for attempt in range(4):
                try:
                    last = find_last_page(issue)
                    break
                except Exception as e:
                    print(f"{issue}: end detect retry ({e})", flush=True)
                    time.sleep(12)
            else:
                last = entry.get("last_page", 48)
            entry["last_page"] = last
            known = {h["page"] for h in entry["hits"]}
            failed = set(ERRORED.get(issue, []))
            # pages never reported (success or error) — scan anything up to last
            pages = [p for p in range(1, last + 1) if p not in known]
        else:
            pages = ERRORED.get(issue, [])
            failed = set(pages)
        print(f"{issue}: re-checking {len(pages)} pages (last={entry['last_page']})", flush=True)
        for p in pages:
            try:
                text = fetch_with_retry(issue, p)
            except Exception as e:
                print(f"{issue} p{p}: STILL FAILING {e}", flush=True)
                continue
            failed.discard(p)
            low = text.lower()
            idx = -1
            for term in ("kaufman", "kaufmann", "koufman"):
                idx = low.find(term)
                if idx >= 0:
                    break
            if idx >= 0:
                ctx = text[max(0, idx - 600): idx + 900]
                entry["hits"].append({"page": p, "context": ctx})
                print(f"{issue} p{p}: *** KAUFMAN HIT ***", flush=True)
            time.sleep(1.2)
        entry["hits"].sort(key=lambda h: h["page"])
        entry["unscanned_pages"] = sorted(failed)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"== {issue} cleanup done ==", flush=True)
    print(json.dumps({k: [h["page"] for h in v["hits"]] for k, v in report.items()}, indent=2))


if __name__ == "__main__":
    sys.exit(main())
