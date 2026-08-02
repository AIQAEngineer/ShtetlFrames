"""Fetch iVelt forum threads via Scrapfly for QA Engineer post extraction."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for env_path in (ROOT / ".env", ROOT / "secrets" / ".env"):
    if not env_path.exists():
        continue
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

from britishpathe import _scrapfly_api_key, scrapfly_fetch_html  # noqa: E402

OUT = ROOT / "output" / "ivelt_qa"
OUT.mkdir(parents=True, exist_ok=True)

URLS = [
    "https://www.ivelt.com/forum/viewtopic.php?t=83177",
    "https://www.ivelt.com/forum/viewtopic.php?t=83175",
    "https://www.ivelt.com/forum/viewtopic.php?p=6846999",
]


def main() -> None:
    print("scrapfly key present:", bool(_scrapfly_api_key()))
    for url in URLS:
        slug = re.sub(r"[^0-9a-zA-Z]+", "_", url.split("viewtopic.php?")[-1])
        path = OUT / f"{slug}.html"
        print("fetching", url)
        try:
            html = scrapfly_fetch_html(url, render_js=True)
        except Exception as exc:  # noqa: BLE001
            print("ERR", url, type(exc).__name__, exc)
            continue
        path.write_text(html, encoding="utf-8")
        print("saved", path, "bytes", len(html))
        # quick peek for author names
        authors = sorted(set(re.findall(r'class="username"[^>]*>([^<]+)<', html)))
        print("usernames sample:", authors[:20])


if __name__ == "__main__":
    main()
