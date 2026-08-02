import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from config import DATA_DIR

url = None
for line in (DATA_DIR / "europeana" / "resolve_media.jsonl").open(encoding="utf-8"):
    if not line.strip():
        continue
    u = json.loads(line)["url"]
    if "euscreen.eu" in u and "item.html" in u:
        url = u
        break

print(f"probe: {url}")
proc = subprocess.run(
    [sys.executable, "-m", "yt_dlp", "--simulate", "--no-warnings", "-4", url],
    capture_output=True,
    text=True,
    timeout=120,
)
out = (proc.stdout or "").strip().splitlines()
err = (proc.stderr or "").strip().splitlines()
print("OK" if proc.returncode == 0 else f"FAIL rc={proc.returncode}")
for ln in out[:4] + err[-4:]:
    print(f"| {ln[:160]}")
