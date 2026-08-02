"""Find Dr. Kaufman's Palestine articles and extract place names."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaufman_notice_scan import OUT_DIR, scrapfly_text, strip_html

PLACE_RE = re.compile(
    r"\b(?:"
    r"Poland|Polish|Warsaw|Kutno|Otwock|Krakow|Cracow|Lwow|Lviv|Berlin|Germany|"
    r"Vienna|Austria|Budapest|Hungary|Prague|Czechoslovakia|"
    r"Jerusalem|Haifa|Tel[\s\-]?Aviv|Jaffa|Hebron|Safed|Galilee|Negev|"
    r"Egypt|Cairo|Italy|Rome|Paris|France|Central Europe|Near East|"
    r"kibbutz|kvutzah|kvutza|colony|Emek|Sharon|Jordan"
    r")\b",
    re.I,
)

ISSUES = [
    "JW19351018",
    "JW19351025",
    "JW19351101",
    "JW19351108",
    "JW19351115",
    "JW19351122",
    "JW19351129",
    "JW19351206",
    "JW19360103",
    "JW19360110",
    "JW19360117",
]


def interesting(low: str) -> bool:
    if "by dr. bernard kaufman" in low:
        return True
    if "says dr. kaufman" in low or "says dr. bernard" in low:
        return True
    if "dr. bernard kaufman" in low and (
        "while visit" in low
        or "as he found" in low
        or "installment" in low
        or "illuminating article" in low
    ):
        return True
    return False


def main() -> None:
    hits = []
    for iss in ISSUES:
        print("ISSUE", iss, flush=True)
        for p in range(1, 90):
            try:
                t = strip_html(
                    scrapfly_text(
                        "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=da&command=getSectionText"
                        f"&d={iss}.2.{p}&srpos=&f=AJAX&e=-------en--20--1--txt-txIN--------"
                    )
                )
            except Exception as e:
                if "404" in str(e):
                    break
                continue
            low = t.lower()
            if not interesting(low):
                continue
            places = sorted({m.group(0) for m in PLACE_RE.finditer(t)})
            print(iss, f"p{p}", places, flush=True)
            print(t[:700], "\n====", flush=True)
            path = os.path.join(OUT_DIR, f"{iss}_p{p}_kaufman_article.txt")
            open(path, "w", encoding="utf-8").write(t)
            hits.append(
                {
                    "issue": iss,
                    "page": p,
                    "places": places,
                    "path": path,
                    "excerpt": t[:1000],
                }
            )
    out = os.path.join(OUT_DIR, "kaufman_articles.json")
    json.dump(hits, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("ARTICLES", len(hits), "->", out)


if __name__ == "__main__":
    sys.exit(main())
