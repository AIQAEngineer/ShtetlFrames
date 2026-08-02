"""Smoke-test local provider resolvers (no Scrapfly required for most)."""

from __future__ import annotations

import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from provider_resolvers import resolve_media_url, resolver_name  # noqa: E402

SAMPLES = [
    (
        "filmarkivet",
        "https://www.filmarkivet.se/movies/komische-begegnungen-im-tiergarten-zu-stockholm/",
    ),
    (
        "nrk",
        "https://tv.nrk.no/serie/filmavisen/FMAA41000441/08-09-1941",
    ),
    ("tib", "https://av.tib.eu/media/16197"),
    (
        "luce",
        "https://patrimonio.archivioluce.com/luce-web/detail/IL5000038685/2/",
    ),
    (
        "elonet",
        "https://elonet.finna.fi/Record/kavi.elonet_elokuva_101153",
    ),
    (
        "nb",
        "https://www.nb.no/items/URN:NBN:no-nb_digifilm_104637_20150126",
    ),
]


def _probe(url: str) -> tuple[int | str, str]:
    try:
        r = requests.head(
            url,
            timeout=25,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        return r.status_code, r.headers.get("Content-Type", "?")[:40]
    except Exception as e:
        return f"err {e}"[:60], "?"


def main() -> int:
    ok = fail = 0
    for expect, page in SAMPLES:
        name = resolver_name(page) or "?"
        media = resolve_media_url(page)
        if not media:
            print(f"FAIL resolve [{expect}/{name}] {page}")
            fail += 1
            continue
        code, ctype = _probe(media)
        good = code in (200, 206) or (
            isinstance(code, int) and code < 400 and "mpegurl" in ctype.lower()
        )
        # HLS playlists sometimes return 200 only on GET
        if not good and ".m3u8" in media.lower():
            try:
                g = requests.get(
                    media,
                    timeout=25,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": page,
                    },
                    stream=True,
                )
                good = g.status_code == 200 and (
                    "#EXT" in g.text[:200]
                    or "mpegurl" in (g.headers.get("Content-Type") or "").lower()
                )
                code = g.status_code
                g.close()
            except Exception as e:
                code = f"get-err {e}"[:40]
        # NB wow CDN may geo-gate cloud IPs; resolve still succeeded.
        soft = (
            not good
            and expect == "nb"
            and "wow.nb.no" in media
            and isinstance(code, int)
        )
        status = "OK  " if good else ("SOFT" if soft else "FAIL")
        if good or soft:
            ok += 1
        else:
            fail += 1
        print(
            f"{status} [{expect}] HTTP {code} type={ctype}\n"
            f"      page:  {page}\n"
            f"      media: {media[:160]}"
        )
    print(f"\nsuccess: {ok}/{ok + fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
