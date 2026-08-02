"""Cinemateca Portuguesa digital catalog resolver.

Ficha.aspx pages embed player.vimeo.com — return the Vimeo URL for yt-dlp.
"""

from __future__ import annotations

from provider_html import extract_vimeo, fetch_html


def is_cinemateca_url(url: str) -> bool:
    u = (url or "").lower()
    return "cinemateca.pt" in u


def resolve_media_url(url: str) -> str | None:
    if not is_cinemateca_url(url):
        return None
    try:
        html = fetch_html(url, scrapfly_fallback=False)
    except Exception:
        return None
    return extract_vimeo(html)
