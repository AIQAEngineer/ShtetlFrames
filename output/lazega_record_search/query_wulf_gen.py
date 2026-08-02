# -*- coding: utf-8 -*-
"""Wulf/Mirla generation Geneteka + related searches (date-bounded)."""
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
        "from_date": kw.get("from_date", "1800"),
        "to_date": kw.get("to_date", "1900"),
        "exac": kw.get("exac", "0"),
        "rpp1": "0",
        "rpp2": "100",
        "draw": "1",
        "start": "0",
        "length": "100",
    }
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


def run(label, **kw):
    j, url = get_acts(**kw)
    rows = clean(j.get("data") or [])
    n = int(j.get("recordsFiltered") or 0)
    print(f"{label}: {n}")
    return {"n": n, "rows": rows[:80], "url": url, "params": kw}


def main():
    hits = {}
    # Broad Lazega in SK with dates (baseline)
    hits["SK_Lazega_B_1800_1900"] = run("SK Lazega B", surname="Lazega", bdm="B", from_date="1800", to_date="1900")
    hits["SK_Lazega_D_1800_1900"] = run("SK Lazega D", surname="Lazega", bdm="D", from_date="1800", to_date="1900")
    hits["SK_Lazega_S_1800_1900"] = run("SK Lazega S", surname="Lazega", bdm="S", from_date="1800", to_date="1900")
    hits["SK_Lazenga_B"] = run("SK Lazenga B", surname="Lazenga", bdm="B", from_date="1800", to_date="1900")
    hits["SK_Lazenga_D"] = run("SK Lazenga D", surname="Lazenga", bdm="D", from_date="1800", to_date="1900")
    hits["SK_Lazenga_S"] = run("SK Lazenga S", surname="Lazenga", bdm="S", from_date="1800", to_date="1900")

    # Byk marriages (Gitla)
    hits["SK_Byk_S"] = run("SK Byk S", surname="Byk", bdm="S", from_date="1820", to_date="1840")
    hits["SK_Byk_Gitla"] = run("SK Byk+Gitla S", surname="Byk", name="Izrael", surname2="Lazega", name2="Gitla", bdm="S", from_date="1825", to_date="1835")
    hits["SK_Lazega_Gitla_S"] = run("SK Lazega Gitla S", surname="Lazega", name="Gitla", bdm="S", from_date="1820", to_date="1840")
    hits["SK_Lazega_Gitla_B"] = run("SK Lazega Gitla B", surname="Lazega", name="Gitla", bdm="B", from_date="1800", to_date="1830")
    hits["SK_Lazega_Gitla_D"] = run("SK Lazega Gitla D", surname="Lazega", name="Gitla", bdm="D", from_date="1820", to_date="1900")

    # Cypa / Luft
    hits["SK_Luft_S"] = run("SK Luft S", surname="Luft", bdm="S", from_date="1825", to_date="1860")
    hits["SK_Luft_D"] = run("SK Luft D", surname="Luft", bdm="D", from_date="1830", to_date="1890")
    hits["SK_Lazega_Cypa_D"] = run("SK Lazega Cypa D", surname="Lazega", name="Cypa", bdm="D", from_date="1860", to_date="1890")
    hits["SK_Lazega_Cypra_D"] = run("SK Lazega Cypra D", surname="Lazega", name="Cypra", bdm="D", from_date="1860", to_date="1890")
    hits["SK_Luft_Cypa_D"] = run("SK Luft Cypa D", surname="Luft", name="Cypa", bdm="D", from_date="1860", to_date="1890")

    # Mirla / Mira deaths & marriages
    for nm in ["Mirla", "Mira", "Mirel", "Mirla"]:
        hits[f"SK_Lazega_{nm}_D"] = run(f"SK Lazega {nm} D", surname="Lazega", name=nm, bdm="D", from_date="1830", to_date="1900")
        hits[f"SK_{nm}_D"] = run(f"SK {nm} D no surn", surname="", name=nm, bdm="D", from_date="1830", to_date="1880")

    # Wolf/Wulf
    for nm in ["Wolf", "Wulf", "Wolff"]:
        hits[f"SK_Lazega_{nm}_D"] = run(f"SK Lazega {nm} D", surname="Lazega", name=nm, bdm="D", from_date="1840", to_date="1860")
        hits[f"SK_Lazega_{nm}_S"] = run(f"SK Lazega {nm} S", surname="Lazega", name=nm, bdm="S", from_date="1800", to_date="1840")

    # Ojzer as surname / given
    hits["SK_Ojzer_B"] = run("SK Ojzer B", surname="Ojzer", bdm="B", from_date="1780", to_date="1860")
    hits["SK_Ojzer_D"] = run("SK Ojzer D", surname="Ojzer", bdm="D", from_date="1780", to_date="1860")
    hits["SK_Ojzer_S"] = run("SK Ojzer S", surname="Ojzer", bdm="S", from_date="1780", to_date="1860")
    hits["SK_name_Ojzer_B"] = run("SK given Ojzer B", surname="", name="Ojzer", bdm="B", from_date="1780", to_date="1860")

    # Children possibly of Wulf: search father Wolf/Wulf + mother Mirla among Lazega
    # Geneteka doesn't take father filter directly; search surname Lazega births 1800-1830 and filter client-side
    base = hits["SK_Lazega_B_1800_1900"]["rows"]
    early = [r for r in base if r and str(r[0]).isdigit() and int(r[0]) <= 1835]
    wulf_kids = [
        r
        for r in early
        if any(x in " ".join(map(str, r)).lower() for x in ["wolf", "wulf", "mirla", "mira"])
    ]
    hits["client_filter_early_Lazega_B_WulfMirla"] = {"n": len(wulf_kids), "rows": wulf_kids}

    # Rochla Lazega as mother (Berkowicz cluster expansion)
    hits["SK_mother_Lazega_B"] = run(
        "SK any B with Lazega (may hit mothers)",
        surname="Lazega",
        bdm="B",
        from_date="1810",
        to_date="1830",
    )

    (OUT / "geneteka_wulf_generation.json").write_text(
        json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    nonzero = {k: v for k, v in hits.items() if v.get("n")}
    print("NONZERO", len(nonzero), "of", len(hits))
    for k, v in nonzero.items():
        print(" ", k, v["n"])


if __name__ == "__main__":
    main()
