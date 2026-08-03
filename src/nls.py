"""NLS Moving Image (movingimage.nls.uk) media resolver.

yt-dlp's MovingImage extractor GETs the film page and reads JWPlayer
``file: "...m3u8"``. Plain / datacenter fetches hit AWS WAF (HTTP 405 Human
Verification). Scrapfly ASP returns the real page; we extract the HLS URL and
hand it to the pod as a plain m3u8 download.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_FILM_RE = re.compile(r"movingimage\.nls\.uk/film/(?P<id>\d+)", re.I)
_JW_FILE_RE = re.compile(r'file\s*:\s*"(https?://[^"]+\.m3u8[^"]*)"', re.I)
_M3U8_RE = re.compile(r'https?://[^\s"\'<>]+?\.m3u8(?:\?[^\s"\'<>]*)?', re.I)


def is_nls_url(url: str) -> bool:
    return bool(_FILM_RE.search(url or ""))


def nls_film_id(url: str) -> str | None:
    m = _FILM_RE.search(url or "")
    return m.group("id") if m else None


def resolve_media_url(url: str) -> str | None:
    """Map a Moving Image film page to an HLS m3u8 URL (or None)."""
    if not is_nls_url(url):
        return None
    try:
        p = urlparse(url)
        page = f"https://movingimage.nls.uk{p.path}"
    except Exception:
        page = url
    html = ""
    # Prefer Scrapfly GB (plain US requests → WAF 405 / Scrapfly 422).
    try:
        from britishpathe import scrapfly_fetch_html

        html = scrapfly_fetch_html(page, render_js=False, country="gb")
    except Exception:
        html = ""
    if not html or "Human Verification" in html[:1200] or not (
        _JW_FILE_RE.search(html) or _M3U8_RE.search(html)
    ):
        try:
            from britishpathe import scrapfly_fetch_html

            html = scrapfly_fetch_html(
                page, render_js=True, rendering_wait=5000, country="gb"
            )
        except Exception:
            if not html:
                return None
    if not html or "Human Verification" in html[:1200]:
        return None
    m = _JW_FILE_RE.search(html)
    if m:
        return m.group(1).rstrip("\\")
    for u in _M3U8_RE.findall(html):
        u = u.rstrip("\\").rstrip("\\'")
        if u:
            return u
    return None
