"""Dump full text of specific iVelt posts."""
from __future__ import annotations

import html as htmlmod
import re
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "output" / "ivelt_qa"

TARGETS = {
    "t_83175.html": ["p6848591", "p6848364", "p6848456"],
    "t_83177.html": ["p6848541"],
    "p_6846999.html": ["p6846999", "p6846293"],
}


def post_chunk(raw: str, pid: str) -> str | None:
    pat = rf'<div id="{pid}".*?(?=<div id="p\d+" class="post |<div id="page-footer")'
    m = re.search(pat, raw, re.S)
    return m.group(0) if m else None


def body_text(chunk: str) -> str:
    cm = re.search(r'<div class="content">(.*)', chunk, re.S)
    body = cm.group(1) if cm else chunk
    text = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = htmlmod.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def main() -> None:
    for fname, pids in TARGETS.items():
        raw = (OUT / fname).read_text(encoding="utf-8")
        for pid in pids:
            chunk = post_chunk(raw, pid)
            path = OUT / f"{pid}_full.txt"
            if not chunk:
                path.write_text("NOT FOUND\n", encoding="utf-8")
                print(pid, "NOT FOUND")
                continue
            text = body_text(chunk)
            path.write_text(text, encoding="utf-8")
            print(pid, "chars", len(text), "->", path.name)


if __name__ == "__main__":
    main()
