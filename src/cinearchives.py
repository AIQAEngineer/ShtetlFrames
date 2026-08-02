"""Cinéarchives (cinearchives.org) — Diaz Interegio oEmbed → progressive MP4."""

from __future__ import annotations

import html as htmlmod
import re
from urllib.parse import urljoin

from provider_html import fetch_html

_IFRAME_RE = re.compile(
    r'<iframe[^>]+src=["\']([^"\']*diaz[^"\']+)["\']',
    re.I,
)
_MP4_SRC_RE = re.compile(
    r'(?:src|href)=["\']([^"\']+\.mp4[^"\']*)["\']',
    re.I,
)


def is_cinearchives_url(url: str) -> bool:
    return "cinearchives.org" in (url or "").lower()


def resolve_media_url(url: str) -> str | None:
    if not is_cinearchives_url(url):
        return None
    page = htmlmod.unescape(url or "")
    try:
        html = fetch_html(page, scrapfly_fallback=False)
    except Exception:
        return None
    m = _IFRAME_RE.search(html or "")
    if not m:
        return None
    embed = urljoin(page, htmlmod.unescape(m.group(1)))
    try:
        embed_html = fetch_html(embed, scrapfly_fallback=False)
    except Exception:
        return None
    m2 = _MP4_SRC_RE.search(embed_html or "")
    if not m2:
        return None
    return urljoin(embed, htmlmod.unescape(m2.group(1)))
