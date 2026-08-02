"""Tick 2: CDNC date-filtered search for Kaufman + European place names."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kaufman_notice_scan import scrapfly_text, strip_html

PLACE = re.compile(
    r"\b(?:Poland|Polish|Warsaw|Kutno|Otwock|Krakow|Cracow|Lwow|Berlin|"
    r"Germany|Vienna|Austria|Budapest|Hungary|Prague|Italy|Rome|Naples|"
    r"Genoa|Paris|France|Central Europe|Europe)\b",
    re.I,
)

URLS = {
    "eu_1934_37": (
        "https://cdnc.ucr.edu/?a=q&hs=1&r=1&results=1"
        "&txq=%22Bernard+Kaufman%22+(Europe+OR+Poland+OR+Warsaw+OR+Berlin"
        "+OR+Vienna+OR+Budapest+OR+Prague+OR+Italy)"
        "&dafdq=01&damfq=01&dayfq=01&dafyq=1934"
        "&datdq=31&damtq=12&daytq=31&datyq=1937"
        "&txf=txIN&ssnip=txt&e=-------en--20--1--txt-txIN--------"
    ),
    "poland_1934_37": (
        "https://cdnc.ucr.edu/?a=q&hs=1&r=1&results=1"
        "&txq=%22Bernard+Kaufman%22+(Poland+OR+Polish+OR+Warsaw+OR+Kutno+OR+Otwock)"
        "&dafdq=01&damfq=01&dayfq=01&dafyq=1934"
        "&datdq=31&damtq=12&daytq=31&datyq=1937"
        "&txf=txIN&ssnip=txt&e=-------en--20--1--txt-txIN--------"
    ),
    "kaufman_1935_36": (
        "https://cdnc.ucr.edu/?a=q&hs=1&r=1&results=1"
        "&txq=%22Dr.+Bernard+Kaufman%22"
        "&dafdq=01&damfq=05&dayfq=01&dafyq=1935"
        "&datdq=31&damtq=12&daytq=31&datyq=1936"
        "&txf=txIN&ssnip=txt&e=-------en--20--1--txt-txIN--------"
    ),
}


def extract_hits(html: str) -> list[str]:
    text = strip_html(html)
    out: list[str] = []
    # Veridian numbered results: "19. Title [ARTICLE] Paper Date ... snip"
    for m in re.finditer(
        r"(\d+)\.\s+(.{5,120}?)\s*\[(ARTICLE[^\]]*|PAGE)\]\s*(.{10,200}?)(?=\s*\d+\.\s+|\s*Add to private list|\s*1 2 3|\Z)",
        text,
        re.S,
    ):
        title = " ".join(m.group(2).split())
        meta = " ".join(m.group(4).split())[:220]
        places = sorted(set(PLACE.findall(meta + " " + title)))
        out.append(f"{m.group(1)}. {title} | places={places} | {meta}")
    return out


def main() -> None:
    for label, url in URLS.items():
        print("====", label, flush=True)
        try:
            html = scrapfly_text(url)
        except Exception as e:
            print("ERR", e, flush=True)
            continue
        text = strip_html(html)
        m = re.search(r"of\s+([\d,]+)\s+for", text)
        print("count", m.group(1) if m else "?", "html_len", len(html), flush=True)
        hits = extract_hits(html)
        for h in hits[:40]:
            print(h, flush=True)
        # Extra snips with place + travel cues
        for m in re.finditer(
            r".{0,50}(?:Europe|Poland|Warsaw|Vienna|Berlin|Budapest|Prague|Italy|Naples|Genoa|Central Europe).{0,90}",
            text,
            re.I,
        ):
            s = " ".join(m.group(0).split())
            if any(k in s.lower() for k in ("kaufman", "trip", "travel", "tour", "returned", "sail")):
                print("SNIP:", s[:200], flush=True)


if __name__ == "__main__":
    main()
