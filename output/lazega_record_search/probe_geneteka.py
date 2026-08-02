# -*- coding: utf-8 -*-
import json
import re
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
ctx = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0", "Accept": "*/*", "X-Requested-With": "XMLHttpRequest"}


def fetch(url, data=None):
    req = urllib.request.Request(url, data=data, headers=UA)
    return urllib.request.urlopen(req, context=ctx, timeout=90).read()


def main():
    page_url = "https://geneteka.genealodzy.pl/index.php?op=gt&lang=eng&bdm=D&w=13sk&rid=D"
    html = fetch(page_url).decode("utf-8", "replace")
    (OUT / "geneteka_page.html").write_text(html, encoding="utf-8")

    ajax_hits = re.findall(r"ajax\s*[:=]\s*['\"]([^'\"]+)", html)
    print("ajax_hits", ajax_hits)
    js_srcs = re.findall(r'src="([^"]+\.js[^"]*)"', html)
    print("js", js_srcs[:20])

    # Geneteka historically posts to index.php with op=gt and aaData JSON response
    # Try several known patterns.
    results = {}
    for surname in ["Lazega", "Lazenga", "Łazęga"]:
        for bdm, rid in [("D", "D"), ("B", "B"), ("S", "S")]:
            params = {
                "op": "gt",
                "lang": "eng",
                "bdm": bdm,
                "w": "13sk",
                "rid": rid,
                "search_lastname": surname,
                "search_name": "",
                "search_lastname2": "",
                "search_name2": "",
                "from_date": "1700",
                "to_date": "1900",
                "exac": "0",
                "rpp1": "100",
                # DataTables classic params
                "sEcho": "1",
                "iDisplayStart": "0",
                "iDisplayLength": "100",
                "sSearch": "",
            }
            url = "https://geneteka.genealodzy.pl/index.php?" + urllib.parse.urlencode(params)
            body = fetch(url)
            text = body.decode("utf-8", "replace")
            key = f"{bdm}_{surname}"
            results[key] = {"url": url, "len": len(text), "head": text[:300]}
            # JSON?
            try:
                j = json.loads(text)
                results[key]["json_keys"] = list(j.keys())
                aa = j.get("aaData") or j.get("data") or []
                results[key]["n"] = len(aa)
                results[key]["sample"] = aa[:5]
                print(key, "JSON", len(aa))
            except Exception:
                # look for aaData embedded
                m = re.search(r'"aaData"\s*:\s*(\[.*?\])\s*[,}]', text, re.S)
                if m:
                    try:
                        aa = json.loads(m.group(1))
                        results[key]["n"] = len(aa)
                        results[key]["sample"] = aa[:3]
                        print(key, "embedded aaData", len(aa))
                    except Exception as e:
                        print(key, "embed parse fail", e)
                else:
                    print(key, "not json, len", len(text))

            # Also try POST
            post = urllib.parse.urlencode(params).encode()
            try:
                body2 = fetch("https://geneteka.genealodzy.pl/index.php", data=post)
                t2 = body2.decode("utf-8", "replace")
                try:
                    j2 = json.loads(t2)
                    aa2 = j2.get("aaData") or j2.get("data") or []
                    print(key, "POST JSON", len(aa2))
                    results[key]["post_n"] = len(aa2)
                    results[key]["post_sample"] = aa2[:5]
                except Exception:
                    print(key, "POST not json", len(t2))
            except Exception as e:
                print(key, "POST err", e)

    (OUT / "geneteka_probe.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2)[:200000], encoding="utf-8"
    )


if __name__ == "__main__":
    main()
