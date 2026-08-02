"""EYE Filmmuseum (filmdatabase.eyefilm.nl) media resolver.

Most EYE collection pages embed YouTube (youtube-nocookie). Resolve to a
canonical watch URL so download_entry uses the YouTube path.
"""

from __future__ import annotations

from provider_html import extract_m3u8s, extract_mp4s, extract_youtube, fetch_html


def is_eyefilm_url(url: str) -> bool:
    u = (url or "").lower()
    return "eyefilm.nl" in u or "filmdatabase.eyefilm.nl" in u


def resolve_media_url(url: str) -> str | None:
    if not is_eyefilm_url(url):
        return None
    try:
        html = fetch_html(url, scrapfly_fallback=False)
    except Exception:
        return None
    yt = extract_youtube(html)
    if yt:
        return yt
    mp4s = extract_mp4s(html)
    if mp4s:
        return mp4s[0]
    m3u8s = extract_m3u8s(html)
    return m3u8s[0] if m3u8s else None
