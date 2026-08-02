"""Cineteca di Bologna Cinestore — Flash oxplayer exposes a progressive FLV."""

from __future__ import annotations

import html as htmlmod
import re
from urllib.parse import urljoin

from provider_html import fetch_html

_FLV_RE = re.compile(
    r'filename:\s*["\']([^"\']+\.flv)["\']',
    re.I,
)


def is_cinestore_url(url: str) -> bool:
    u = (url or "").lower()
    return "cinestore.cinetecadibologna.it" in u or "cinetecadibologna.it" in u


def resolve_media_url(url: str) -> str | None:
    if not is_cinestore_url(url):
        return None
    page = htmlmod.unescape(url or "")
    try:
        html = fetch_html(page, scrapfly_fallback=False)
    except Exception:
        return None
    m = _FLV_RE.search(html or "")
    if not m:
        return None
    return urljoin(page, htmlmod.unescape(m.group(1)))
