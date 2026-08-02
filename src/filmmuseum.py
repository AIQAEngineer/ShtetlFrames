"""Austrian Film Museum (filmmuseum.at) resolver — Vimeo embeds."""

from __future__ import annotations

import html as htmlmod

from provider_html import extract_vimeo, fetch_html


def is_filmmuseum_url(url: str) -> bool:
    return "filmmuseum.at" in (url or "").lower()


def resolve_media_url(url: str) -> str | None:
    if not is_filmmuseum_url(url):
        return None
    page = htmlmod.unescape(url or "")
    try:
        html = fetch_html(page, scrapfly_fallback=False)
    except Exception:
        return None
    return extract_vimeo(html)
