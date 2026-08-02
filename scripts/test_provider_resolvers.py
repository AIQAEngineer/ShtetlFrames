"""Smoke-test local provider resolvers against known-good item pages."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from provider_resolvers import can_import_provider_page, needs_resolve, resolve_media_url

SAMPLES = [
    ("filmportal", "https://www.filmportal.de/node/1192000"),
    ("eye", "https://filmdatabase.eyefilm.nl/en/node/123269/"),
    ("cinemateca", "http://www.cinemateca.pt/Cinemateca-Digital/Ficha.aspx?obraid=8353&type=Video"),
    ("stumfilm", "https://www.stumfilm.dk/stumfilm/streaming/film/21662"),
    ("filmarkivet", "https://www.filmarkivet.se/movies/bilder-fran-telegrafverket/"),
    ("iwm", "https://www.iwm.org.uk/collections/item/object/1060023126"),
    ("nls-native", "https://movingimage.nls.uk/film/1062"),  # yt-dlp native, no resolver
    ("vimeo-native", "https://vimeo.com/155357957"),
]


def main() -> int:
    failed = 0
    for name, url in SAMPLES:
        print(f"==== {name}")
        print(f"  needs_resolve={needs_resolve(url)} can_import={can_import_provider_page(url)}")
        if not needs_resolve(url):
            print("  (yt-dlp / passthrough — skip resolve)")
            continue
        try:
            got = resolve_media_url(url)
        except Exception as e:
            print(f"  ERR {type(e).__name__}: {e}")
            failed += 1
            continue
        print(f"  -> {got}")
        if not got:
            failed += 1
    print(f"failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
