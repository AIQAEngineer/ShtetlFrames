"""Danish Film Institute Stumfilm (stumfilm.dk) resolver.

Streaming pages carry a Vimeo embed in a JSON data attribute.
"""

from __future__ import annotations

from provider_html import extract_vimeo, fetch_html


def is_stumfilm_url(url: str) -> bool:
    u = (url or "").lower()
    return "stumfilm.dk" in u


def resolve_media_url(url: str) -> str | None:
    if not is_stumfilm_url(url):
        return None
    try:
        html = fetch_html(url, scrapfly_fallback=False)
    except Exception:
        return None
    return extract_vimeo(html)
