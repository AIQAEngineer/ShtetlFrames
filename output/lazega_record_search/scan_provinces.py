# -*- coding: utf-8 -*-
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
    provinces = [
        "13sk", "06mp", "10pl", "07mz", "03lb", "05ld", "12sl", "02kp",
        "01ds", "04ls", "08op", "09pk", "11pm", "14wm", "15wp", "16zp", "17wa",
    ]
    hits = {}
    for w in provinces:
        for surname in ["Lazega", "Lazenga", "Lazegowna"]:
            for bdm in ["B", "D", "S"]:
                j, url = get_acts(
                    w=w, bdm=bdm, surname=surname, name="", from_date="1800", to_date="1860"
                )
                n = int(j.get("recordsFiltered") or 0)
                key = f"{w}|{bdm}|{surname}"
                if n:
                    hits[key] = {"n": n, "rows": clean(j.get("data") or [])[:40], "url": url}
                    print("HIT", key, n)
                else:
                    print("miss", key)

        # known PDF Geneteka lead: Mortka Berkowicz 1814 mother Rochla Lazega
        j, url = get_acts(w=w, bdm="B", surname="Berkowicz", name="Mortka", from_date="1810", to_date="1820")
        n = int(j.get("recordsFiltered") or 0)
        if n:
            hits[f"{w}|B|Berkowicz|Mortka"] = {
                "n": n,
                "rows": clean(j.get("data") or [])[:20],
                "url": url,
            }
            print("HIT", f"{w}|B|Berkowicz|Mortka", n)

    (OUT / "geneteka_province_scan.json").write_text(
        json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("TOTAL HIT KEYS", len(hits))


if __name__ == "__main__":
    main()
