import json
import re

p = r"C:\Users\Avi Schwartz\.cursor\browser-logs\cdp-response-Runtime.evaluate-2026-08-02T16-23-26-103Z.json"
with open(p, encoding="utf-8") as f:
    d = json.load(f)

val = None
try:
    val = d["result"]["result"]["value"]
except Exception:
    pass
if val is None:
    def find_value(o):
        if isinstance(o, dict):
            if "value" in o and isinstance(o["value"], dict) and "text" in o.get("value", {}):
                return o["value"]
            for v in o.values():
                r = find_value(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = find_value(v)
                if r:
                    return r
        return None
    val = find_value(d)

if not val:
    print("NO VAL", type(d), str(d)[:500])
    raise SystemExit(1)

text = val.get("text", "")
print("TEXT_LEN", len(text))
out_path = r"C:\Users\Avi Schwartz\Documents\hasidic-footage-scan\output\lazega_record_search\jri_lazega_kielce.txt"
with open(out_path, "w", encoding="utf-8") as out:
    out.write(text)
    out.write("\n\n=== TABLES ===\n")
    for t in val.get("tables", []):
        out.write(f"\nTABLE {t['i']} rows={t['rowCount']}\n")
        for r in t["rows"]:
            out.write(r + "\n")

# print filtered interesting lines
pat = re.compile(r"Lazega|Łaz|Abram|Wolf|Wulf|Mirla|Benjamin|Beniamin|Hersz|Ojzer|Gitla|Cypa", re.I)
for line in text.splitlines():
    if pat.search(line):
        print(line[:400])
print("WROTE", out_path)
