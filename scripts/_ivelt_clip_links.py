"""Extract https links and img src from QA Engineer posts in p_6846999.html."""
from __future__ import annotations

import html as htmlmod
import re
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "output" / "ivelt_qa" / "p_6846999.html"
OUT = Path(__file__).resolve().parents[1] / "output" / "ivelt_qa" / "clip_links.txt"

PIDS = [
    "p6845287",
    "p6845327",
    "p6845554",
    "p6845615",
    "p6845893",
    "p6845860",
    "p6845928",
    "p6846999",
]


def main() -> None:
    raw = RAW.read_text(encoding="utf-8")
    lines: list[str] = []
    for pid in PIDS:
        m = re.search(
            rf'<div id="{pid}".*?(?=<div id="p\d+" class="post |<div id="page-footer")',
            raw,
            re.S,
        )
        lines.append(f"==== {pid}")
        if not m:
            lines.append("MISSING")
            continue
        ch = m.group(0)
        title = re.search(r"<strong[^>]*>([^<]+)</strong>", ch)
        if title:
            lines.append("TITLE: " + htmlmod.unescape(title.group(1)))
        for link in re.findall(r'href="(https?://[^"]+)"', ch):
            lines.append("LINK: " + htmlmod.unescape(link))
        for img in re.findall(r'src="([^"]+)"', ch)[:12]:
            lines.append("IMG: " + htmlmod.unescape(img)[:160])
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
