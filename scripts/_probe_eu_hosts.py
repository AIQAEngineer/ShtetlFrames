import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from config import DATA_DIR

samples = {}
for line in (DATA_DIR / "europeana" / "resolve_media.jsonl").open(encoding="utf-8"):
    if not line.strip():
        continue
    u = json.loads(line)["url"]
    for key in ("patrimonio.archivioluce.com", "www.euscreen.eu", "tv.nrk.no", "www.iwm.org.uk"):
        if key in u and key not in samples:
            samples[key] = u
    if len(samples) >= 4:
        break

for host, url in samples.items():
    print(f"== {host}\n   {url}")
    proc = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--simulate", "--no-warnings", "-4", url],
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = (proc.stdout or "").strip().splitlines()
    err = (proc.stderr or "").strip().splitlines()
    verdict = "OK" if proc.returncode == 0 else "FAIL"
    print(f"   {verdict} rc={proc.returncode}")
    for ln in (out[:3] + err[-3:]):
        print(f"   | {ln[:150]}")
