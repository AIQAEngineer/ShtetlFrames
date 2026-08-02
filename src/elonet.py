"""Elonet / Finna (elonet.finna.fi) media resolver.

Record pages sit behind a soft block for plain bots; Scrapfly returns HTML
with an icareus / CloudFront HLS playlist.
"""

from __future__ import annotations

from provider_html import extract_m3u8s, extract_mp4s, extract_youtube, fetch_html


def is_elonet_url(url: str) -> bool:
    u = (url or "").lower()
    return "elonet.finna.fi" in u or "elonet.fi" in u


def resolve_media_url(url: str) -> str | None:
    if not is_elonet_url(url):
        return None
    try:
        html = fetch_html(url, scrapfly_fallback=True)
    except Exception:
        return None
    m3u8s = extract_m3u8s(html)
    if m3u8s:
        return m3u8s[0]
    mp4s = extract_mp4s(html)
    if mp4s:
        return mp4s[0]
    return extract_youtube(html)
