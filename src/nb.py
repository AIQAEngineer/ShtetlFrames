"""National Library of Norway (nb.no / urn.nb.no) media resolver.

Item pages redirect to www.nb.no/items/<URN>. The IIIF v3 manifest exposes a
Wowza HLS playlist on wow.nb.no — no Scrapfly needed.
"""

from __future__ import annotations

import html as htmlmod
import json
import re
import urllib.parse
import urllib.request

_URN_RE = re.compile(r"(URN:NBN:no-nb_[A-Za-z0-9_-]+)", re.I)
_M3U8_RE = re.compile(r'https?://[^\s"\\]+?\.m3u8(?:\?[^\s"\\]*)?', re.I)


def is_nb_url(url: str) -> bool:
    u = (url or "").lower()
    return "urn.nb.no" in u or "nb.no" in u and ("urn:nbn:" in u or "/items/" in u)


def extract_urn(url: str) -> str | None:
    text = htmlmod.unescape(url or "")
    # Path form: /items/URN:NBN:... or bare URN on urn.nb.no
    m = _URN_RE.search(urllib.parse.unquote(text))
    return m.group(1) if m else None


def resolve_media_url(url: str) -> str | None:
    if not is_nb_url(url):
        return None
    urn = extract_urn(url)
    if not urn:
        return None
    api = f"https://api.nb.no/catalog/v3/iiif/{urn}/manifest"
    req = urllib.request.Request(
        api, headers={"User-Agent": "ShtetlFrames/1.0 (nb)", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    blob = json.dumps(data)
    # Prefer wow.nb.no VOD playlists from the painting annotation body.
    m3us = _M3U8_RE.findall(blob)
    for u in m3us:
        if "wow.nb.no" in u.lower() or "playlist.m3u8" in u.lower():
            return u.rstrip("\\")
    return m3us[0].rstrip("\\") if m3us else None
