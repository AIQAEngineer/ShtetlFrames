"""Fetch Pathé asset pages for QA clip IDs via Scrapfly."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
for env_path in (ROOT / ".env", ROOT / "secrets" / ".env"):
    if not env_path.exists():
        continue
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from britishpathe import scrapfly_fetch_html  # noqa: E402

OUT = ROOT / "output" / "ivelt_qa"
ASSETS = {
    "86316": "Jerusalem 1964",
    "206920": "Eilat 1957",
    "38248": "Jerusalem 1967",
    "64645": "Brooklyn cards 1932",
    "259561": "Pathé Jewish Life",
}


def main() -> None:
    lines: list[str] = []
    for aid, label in ASSETS.items():
        url = f"https://www.britishpathe.com/asset/{aid}/"
        lines.append(f"==== {aid} ({label})")
        try:
            html = scrapfly_fetch_html(url, render_js=True, rendering_wait=5000)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"ERR {type(exc).__name__}: {exc}")
            continue
        (OUT / f"pathe_{aid}.html").write_text(html, encoding="utf-8")
        title = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        if title:
            t = re.sub(r"<[^>]+>", "", title.group(1)).strip()
            lines.append(f"TITLE: {t}")
        # issue date
        for pat in [
            r"Issue Date:</[^>]+>\s*<[^>]+>([^<]+)",
            r"Issue Date</[^>]+>\s*<[^>]+>([^<]+)",
            r'"issueDate"\s*:\s*"([^"]+)"',
            r"Issue Date[:\s]+([0-9/.\-A-Za-z ]+)",
        ]:
            m = re.search(pat, html, re.I)
            if m:
                lines.append(f"DATE: {m.group(1).strip()}")
                break
        # short summary
        desc = re.search(r"Short Summary</[^>]+>\s*<[^>]+>(.*?)</", html, re.S | re.I)
        if not desc:
            desc = re.search(r'<meta name="description" content="([^"]+)"', html)
        if desc:
            d = re.sub(r"<[^>]+>", "", desc.group(1)).strip()
            lines.append(f"SUMMARY: {d[:400]}")
        # description block
        body = re.search(
            r'<div class="description[^"]*">(.*?)</div>',
            html,
            re.S | re.I,
        )
        if body:
            b = re.sub(r"<[^>]+>", " ", body.group(1))
            b = re.sub(r"\s+", " ", b).strip()
            lines.append(f"DESC: {b[:800]}")
    out = OUT / "pathe_clip_meta.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
