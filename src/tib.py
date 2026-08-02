"""TIB AV-Portal (av.tib.eu) resolver — JWT-ticketed HLS from the media page."""

from __future__ import annotations

import re

from provider_fetch import fetch_html

_MEDIA_RE = re.compile(
    r'https://av\.tib\.eu/resources/media/[^\s"\'<>]+',
    re.I,
)


def is_tib_url(url: str) -> bool:
    u = (url or "").lower()
    return "av.tib.eu" in u and "/media/" in u


def resolve_media_url(url: str) -> str | None:
    if not is_tib_url(url):
        return None
    html = fetch_html(url)
    if not html:
        return None
    urls = list(dict.fromkeys(_MEDIA_RE.findall(html)))
    hls = [u for u in urls if "hls.m3u8" in u.lower() or u.lower().endswith(".m3u8")]
    if hls:
        return hls[0]
    # Prefer progressive over init segments
    prog = [u for u in urls if ".mp4" in u.lower() and "_init" not in u.lower()]
    return prog[0] if prog else (urls[0] if urls else None)
