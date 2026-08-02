# -*- coding: utf-8 -*-
"""Query Geneteka api/getAct.php for Łazęga tree people."""
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
ctx = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/javascript, */*"}


def get_acts(surname, name="", bdm="D", w="13sk", from_date="1700", to_date="1950", length=100, parents=False):
    params = {
        "op": "gt",
        "lang": "eng",
        "bdm": bdm,
        "w": w,
        "rid": bdm,
        "search_lastname": surname,
        "search_name": name,
        "search_lastname2": "",
        "search_name2": "",
        "from_date": from_date,
        "to_date": to_date,
        "exac": "0",
        "rpp1": "0",
        "rpp2": str(length),
        "draw": "1",
        "start": "0",
        "length": str(length),
    }
    if parents:
        # not skipping parents is default; some UIs use parents=1
        params["parents"] = "0"
    url = "https://geneteka.genealodzy.pl/api/getAct.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    raw = urllib.request.urlopen(req, context=ctx, timeout=90).read().decode("utf-8", "replace")
    try:
        return json.loads(raw), url
    except json.JSONDecodeError:
        return {"_raw": raw[:1000]}, url


def rows_from(j):
    data = j.get("data") or j.get("aaData") or []
    out = []
    for row in data:
        if isinstance(row, list):
            # strip HTML
            clean = []
            for cell in row:
                if isinstance(cell, str):
                    import re
                    clean.append(re.sub(r"<[^>]+>", "", cell).strip())
                else:
                    clean.append(cell)
            out.append(clean)
        else:
            out.append(row)
    return out


def main():
    all_results = {}
    searches = []
    # Top of tree: Abram / Abraham as subject and as father
    for surname in ["Lazega", "Lazenga", "Łazęga"]:
        for name in ["", "Abram", "Abraham", "Wulf", "Wolf", "Beniamin", "Benjamin"]:
            for bdm in ["D", "B", "S"]:
                searches.append((surname, name, bdm, "13sk"))
    # Also małopolskie (Wieliczka/Feig area) later; keep first batch świętokrzyskie

    for surname, name, bdm, w in searches:
        key = f"{w}|{bdm}|{surname}|{name or '*'}"
        try:
            j, url = get_acts(surname, name, bdm=bdm, w=w)
            rows = rows_from(j)
            rec = {
                "url": url,
                "recordsTotal": j.get("recordsTotal"),
                "recordsFiltered": j.get("recordsFiltered"),
                "n": len(rows),
                "rows": rows[:80],
                "keys": list(j.keys()) if isinstance(j, dict) else [],
            }
            all_results[key] = rec
            if rows:
                print(f"HIT {key}: {len(rows)} / filtered={rec['recordsFiltered']}")
            else:
                print(f"miss {key}: total={rec['recordsTotal']} filtered={rec['recordsFiltered']}")
        except Exception as e:
            all_results[key] = {"error": str(e)}
            print(f"ERR {key}: {e}")

    (OUT / "geneteka_abram_batch.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Summary of hits only
    hits = {k: v for k, v in all_results.items() if v.get("n")}
    (OUT / "geneteka_abram_hits.json").write_text(
        json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("HITS", len(hits), "of", len(all_results))


if __name__ == "__main__":
    main()
