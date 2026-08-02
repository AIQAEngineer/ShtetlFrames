"""Extract posts by קיו עי אינזשעניר from fetched iVelt HTML."""
from __future__ import annotations

import html as htmlmod
import json
import re
from pathlib import Path

AUTHOR = "קיו עי אינזשעניר"
OUT = Path(__file__).resolve().parents[1] / "output" / "ivelt_qa"


def extract_posts(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    topic_m = re.search(r"<h2[^>]*>(.*?)</h2>", raw, re.S)
    topic = re.sub(r"<[^>]+>", "", topic_m.group(1)).strip() if topic_m else path.name
    topic = htmlmod.unescape(topic)

    posts: list[dict] = []
    chunks = re.split(r'(?=<div id="p\d+" class="post )', raw)
    for ch in chunks:
        m_id = re.search(r'<div id="(p\d+)" class="post ', ch)
        if not m_id:
            continue
        um = re.search(r'class="username[^"]*"[^>]*>([^<]+)<', ch)
        if not um:
            continue
        user = htmlmod.unescape(um.group(1)).strip()
        if AUTHOR not in user:
            continue
        cm = re.search(
            r'<div class="content">(.*?)</div>\s*(?:<div class="(?:notice|signature)|'
            r"</div>\s*</div>\s*<dl class=\"postprofile)",
            ch,
            re.S,
        )
        if not cm:
            cm = re.search(r'<div class="content">(.*?)</div>', ch, re.S)
        body_html = cm.group(1) if cm else ""
        text = re.sub(r"<br\s*/?>", "\n", body_html, flags=re.I)
        text = re.sub(r"</p>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = htmlmod.unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        wm = re.search(r"<time[^>]*>([^<]+)</time>", ch)
        when = wm.group(1).strip() if wm else ""
        links = re.findall(r'href="([^"]+)"', body_html)
        posts.append(
            {
                "file": path.name,
                "topic": topic,
                "post_id": m_id.group(1),
                "user": user,
                "when": when,
                "text": text,
                "links": links,
                "body_html": body_html,
            }
        )
    return posts


def main() -> None:
    all_posts: list[dict] = []
    for path in sorted(OUT.glob("*.html")):
        all_posts.extend(extract_posts(path))
    out_json = OUT / "qa_posts.json"
    out_json.write_text(json.dumps(all_posts, ensure_ascii=False, indent=2), encoding="utf-8")
    print("count", len(all_posts))
    for i, p in enumerate(all_posts):
        print("=" * 70)
        print(f"#{i} {p['file']} {p['post_id']} | {p['when']}")
        print("TOPIC:", p["topic"][:200])
        print(p["text"][:4000])
        print("LINKS:", p["links"][:15])


if __name__ == "__main__":
    main()
