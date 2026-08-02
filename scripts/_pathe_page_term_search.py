import csv
import json
import os
import re
import sqlite3
import sys
import time
from html import unescape

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import DB_PATH, OUTPUT_DIR
from britishpathe import scrapfly_fetch_html, asset_id_from_url

TERMS = ["jew", "jewish", "hebrew", "rabbi", "hasid", "orthodox", "synagogue", "yiddish"]

# Phrases that count as real Jewish content (not jewel/rabbit noise)
STRONG_PHRASES = [
    "jewish", "hebrew", "synagogue", "rabbi", "yiddish", "hasid", "orthodox jew",
    "passover", "seder", "matzah", "matzo", "yom kippur", "rosh hashanah", "zion",
    "zionist", "palestine jew", "israel", "holocaust", "refugee", "rabbinic",
]

TAG_RE = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)
TAG_RE2 = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
TAG_RE3 = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def page_text(html: str) -> str:
    h = TAG_RE.sub(" ", html or "")
    h = TAG_RE2.sub(" ", h)
    h = TAG_RE3.sub(" ", h)
    return SPACE_RE.sub(" ", unescape(h)).strip().lower()


def classify(text: str, title: str):
    strong = [t for t in TERMS if t in text]
    phrase_hits = [p for p in STRONG_PHRASES if p in text]
    # Filter obvious false positives when only "jew" matched via jewellery etc.
    if "jew" in strong and not phrase_hits and "jewish" not in strong:
        if any(x in text for x in ["jewel", "jewellery", "jewelry"]):
            return strong, phrase_hits, False
    return strong, phrase_hits, bool(phrase_hits or "jewish" in strong or "hebrew" in strong)


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, url, title, status
        FROM queue_items
        WHERE url LIKE '%britishpathe.com%' AND status='done'
        """
    ).fetchall()

    # Only fetch assets whose title/URL already matched (the 114) — avoids thousands of Scrapfly calls.
    seed = [r for r in rows if any(t in (r["title"] or "").lower() or t in (r["url"] or "").lower() for t in ["jew", "hebrew", "rabbi"])]
    print(f"fetching {len(seed)} candidate pages…")

    out = OUTPUT_DIR / "pathe_term_search.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    results = []
    for i, r in enumerate(seed, 1):
        url = r["url"]
        aid = asset_id_from_url(url) or ""
        try:
            html = scrapfly_fetch_html(url, render_js=False)
            text = page_text(html)
        except Exception as e:
            results.append({
                "id": r["id"], "asset_id": aid, "title": r["title"], "url": url,
                "error": str(e)[:120], "terms": "", "phrases": "", "strong": 0,
            })
            continue
        terms, phrases, strong = classify(text, r["title"] or "")
        results.append({
            "id": r["id"], "asset_id": aid, "title": r["title"], "url": url,
            "terms": ",".join(terms), "phrases": ",".join(phrases), "strong": 1 if strong else 0,
            "error": "",
        })
        if i % 20 == 0:
            print(f"  {i}/{len(seed)}…")

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "asset_id", "title", "url", "terms", "phrases", "strong", "error"])
        w.writeheader()
        w.writerows(results)

    strong = [r for r in results if r.get("strong")]
    print(f"\nWrote {out} — {len(results)} rows, {len(strong)} strong matches.")
    print("\nTop strong matches:")
    for r in strong[:40]:
        print(f"  • {r['title']}  [{r['phrases'] or r['terms']}] — {r['url']}")


if __name__ == "__main__":
    main()
