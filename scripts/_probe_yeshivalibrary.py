"""Probe yeshivalibrary.org for current catalog size."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "output" / "ivelt_qa"
UA = {"User-Agent": "Mozilla/5.0 (research)"}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode("utf-8", "ignore")


def main() -> None:
    html = fetch("https://yeshivalibrary.org/")
    (OUT / "yeshivalibrary_home.html").write_text(html, encoding="utf-8")
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)', html)
    urls = set(re.findall(r'https?://[^"\']+\.(?:json|js|csv)', html))
    print("scripts:", scripts[:30])
    print("asset urls:", list(urls)[:30])
    for pat in (r"\b1[,.]?650\b", r"\b1[,.]?400\b", r"\b850\b", r"total[^<]{0,40}", r"wolumin"):
        print(pat, re.findall(pat, html, re.I)[:10])
    # common SPA data paths
    for path in (
        "/data/books.json",
        "/books.json",
        "/api/books",
        "/assets/data.json",
        "/static/data.json",
    ):
        try:
            body = fetch("https://yeshivalibrary.org" + path)
            print("HIT", path, "len", len(body), body[:200])
            (OUT / f"yeshivalibrary{path.replace('/', '_')}.txt").write_text(body[:5000], encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print("miss", path, type(exc).__name__)


if __name__ == "__main__":
    main()
