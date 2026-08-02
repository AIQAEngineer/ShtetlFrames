# -*- coding: utf-8 -*-
"""Search Geneteka for Abram as father / given name among Lazega; also broader date ranges."""
from pathlib import Path
import json, ssl, urllib.parse, urllib.request, re, sys

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(__file__).resolve().parent
ctx = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get_acts(**kw):
    params = {
        "op": "gt",
        "lang": "eng",
        "bdm": kw.get("bdm", "B"),
        "w": kw.get("w", "13sk"),
        "rid": kw.get("rid", kw.get("bdm", "B")),
        "search_lastname": kw.get("surname", ""),
        "search_name": kw.get("name", ""),
        "search_lastname2": kw.get("surname2", ""),
        "search_name2": kw.get("name2", ""),
        "from_date": kw.get("from_date", ""),
        "to_date": kw.get("to_date", ""),
        "exac": kw.get("exac", "0"),
        "rpp1": "0",
        "rpp2": "100",
        "draw": "1",
        "start": "0",
        "length": "100",
    }
    # parents=1 means SKIP parents in Geneteka UI; leave unchecked so father Abram matches
    url = "https://geneteka.genealodzy.pl/api/getAct.php?" + urllib.parse.urlencode(params)
    raw = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), context=ctx, timeout=90
    ).read().decode("utf-8", "replace")
    return json.loads(raw), url


def clean(rows):
    out = []
    for row in rows:
        out.append([re.sub(r"<[^>]+>", "", c).strip() if isinstance(c, str) else c for c in row])
    return out


def main():
    hits = {}
    # Search Lazega with given name empty but look for father Abram in results;
    # also search surname empty + name Abram is useless. Better: surname Lazega, no date limit.
    queries = [
        dict(w="13sk", bdm="B", surname="Lazega", name="", from_date="", to_date=""),
        dict(w="13sk", bdm="D", surname="Lazega", name="", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazega", name="", from_date="", to_date=""),
        dict(w="13sk", bdm="B", surname="Lazenga", name="", from_date="", to_date=""),
        dict(w="13sk", bdm="D", surname="Lazenga", name="", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazenga", name="", from_date="", to_date=""),
        # Abram as given name + Lazega
        dict(w="13sk", bdm="B", surname="Lazega", name="Abram", from_date="", to_date=""),
        dict(w="13sk", bdm="D", surname="Lazega", name="Abram", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazega", name="Abram", from_date="", to_date=""),
        dict(w="13sk", bdm="B", surname="Lazega", name="Abraham", from_date="", to_date=""),
        dict(w="13sk", bdm="D", surname="Lazega", name="Abraham", from_date="", to_date=""),
        # Wolf/Wulf as subject
        dict(w="13sk", bdm="D", surname="Lazega", name="Wolf", from_date="", to_date=""),
        dict(w="13sk", bdm="D", surname="Lazega", name="Wulf", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazega", name="Wolf", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazega", name="Wulf", from_date="", to_date=""),
        dict(w="13sk", bdm="B", surname="Lazega", name="Wolf", from_date="", to_date=""),
        # Mirla/Mira
        dict(w="13sk", bdm="D", surname="Lazega", name="Mirla", from_date="", to_date=""),
        dict(w="13sk", bdm="D", surname="Lazega", name="Mira", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazega", name="Mirla", from_date="", to_date=""),
        # Beniamin
        dict(w="13sk", bdm="D", surname="Lazega", name="Beniamin", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazega", name="Beniamin", from_date="", to_date=""),
        dict(w="13sk", bdm="B", surname="Lazega", name="Beniamin", from_date="", to_date=""),
        # Ojzer / related
        dict(w="13sk", bdm="B", surname="Lazega", name="Ojzer", from_date="", to_date=""),
        dict(w="13sk", bdm="D", surname="Lazega", name="Ojzer", from_date="", to_date=""),
        # Herszli household (early New Miasto)
        dict(w="13sk", bdm="B", surname="Lazega", name="Herszli", from_date="", to_date=""),
        dict(w="13sk", bdm="D", surname="Lazega", name="Herszli", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazega", name="Herszli", from_date="", to_date=""),
        dict(w="13sk", bdm="B", surname="Zelmanowicz", name="Laja", from_date="1790", to_date="1860"),
        # Gitla Byk marriage side
        dict(w="13sk", bdm="S", surname="Byk", name="Izrael", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Byk", name="Gitla", from_date="", to_date=""),
        dict(w="13sk", bdm="S", surname="Lazega", name="Gitla", from_date="", to_date=""),
    ]

    for q in queries:
        j, url = get_acts(**q)
        rows = clean(j.get("data") or [])
        n = int(j.get("recordsFiltered") or 0)
        key = f"{q['w']}|{q['bdm']}|{q['surname']}|{q.get('name') or '*'}"
        print(f"{key}: {n}")
        if n:
            # filter rows mentioning Abram/Abraham in any field when searching broadly
            if q.get("name") in ("", None) and q["surname"].startswith("Laz"):
                ab = [r for r in rows if any("Abram" in str(c) or "Abraham" in str(c) for c in r)]
                hits[key] = {"n": n, "rows": rows[:50], "abram_mentions": ab, "url": url}
            else:
                hits[key] = {"n": n, "rows": rows[:50], "url": url}

    (OUT / "geneteka_abram_wulf_focus.json").write_text(
        json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("saved", len(hits), "hit keys")


if __name__ == "__main__":
    main()
