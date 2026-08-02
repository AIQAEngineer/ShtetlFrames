"""mediawien-film.at resolver — progressive MP4 under /media/uploads/videos/."""

from __future__ import annotations

import html as htmlmod
import re
from urllib.parse import urljoin

from provider_html import fetch_html

_SOURCE_RE = re.compile(
    r'<source[^>]+src=["\']([^"\']+\.mp4[^"\']*)["\']',
    re.I,
)


def is_mediawien_url(url: str) -> bool:
    return "mediawien-film.at" in (url or "").lower()


def resolve_media_url(url: str) -> str | None:
    if not is_mediawien_url(url):
        return None
    page = htmlmod.unescape(url or "")
    try:
        html = fetch_html(page, scrapfly_fallback=False)
    except Exception:
        return None
    m = _SOURCE_RE.search(html or "")
    if not m:
        return None
    return urljoin(page, htmlmod.unescape(m.group(1)))
