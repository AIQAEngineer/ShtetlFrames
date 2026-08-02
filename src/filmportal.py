"""filmportal.de media resolver.

EFG `dff::` / filmportal linked_out pages embed either:
- a progressive MP4 under /sites/default/files/video/, or
- a Vimeo/YouTube player via data-src (cookie placeholder iframes).

Plain HTTP works — no Scrapfly.
"""

from __future__ import annotations

from provider_html import (
    extract_mp4s,
    extract_vimeo,
    extract_youtube,
    fetch_html,
)


def is_filmportal_url(url: str) -> bool:
    u = (url or "").lower()
    return "filmportal.de" in u


def resolve_media_url(url: str) -> str | None:
    if not is_filmportal_url(url):
        return None
    try:
        html = fetch_html(url, scrapfly_fallback=False)
    except Exception:
        return None
    mp4s = [
        u for u in extract_mp4s(html)
        if "filmportal.de" in u.lower() and "/video/" in u.lower()
    ]
    if mp4s:
        return mp4s[0]
    yt = extract_youtube(html)
    if yt:
        return yt
    vimeo = extract_vimeo(html)
    if not vimeo:
        return None
    # Return the player embed URL; download_entry passes this page as Referer
    # and yt-dlp --impersonate fetches it (CDN progressive URLs 403 without
    # the player session / TLS fingerprint).
    return vimeo
