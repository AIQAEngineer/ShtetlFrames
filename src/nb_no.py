"""Nasjonalbiblioteket (nb.no / urn.nb.no) resolver via IIIF presentation → HLS."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

import requests

from provider_fetch import UA, find_m3u8s

_URN_RE = re.compile(r"(URN:NBN:no-nb_digifilm_[A-Za-z0-9_]+)", re.I)


def is_nb_url(url: str) -> bool:
    u = (url or "").lower()
    return (
        "urn.nb.no" in u
        or "nb.no/items/" in u
        or "api.nb.no" in u
        or "wow.nb.no" in u
    )


def extract_urn(url: str) -> str | None:
    u = unquote(url or "")
    m = _URN_RE.search(u)
    if m:
        return m.group(1)
    # path form /items/URN:…
    path = urlparse(u).path
    if "URN:NBN:" in path:
        return path.rstrip("/").split("/")[-1]
    return None


def resolve_media_url(url: str, *, timeout: int = 25) -> str | None:
    if not is_nb_url(url):
        return None
    # Already a playlist
    if ".m3u8" in (url or "").lower() and "wow.nb.no" in (url or "").lower():
        return url
    urn = extract_urn(url)
    if not urn:
        return None
    api = f"https://api.nb.no/catalog/v3/iiif/{urn}/manifest"
    try:
        r = requests.get(
            api,
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=timeout,
        )
        r.raise_for_status()
        text = r.text
    except Exception:
        return None
    m3u8s = find_m3u8s(text)
    wow = [u for u in m3u8s if "wow.nb.no" in u.lower()]
    return (wow or m3u8s)[0] if (wow or m3u8s) else None
