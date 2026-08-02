"""Filmarkivet.se media resolver.

Pages configure JWPlayer with an S3 progressive MP4 (`file: "https://...mp4"`).
Commented `//file:` lines are older assets — we take the active `file:` only.
"""

from __future__ import annotations

from provider_html import extract_jw_file, extract_mp4s, fetch_html


def is_filmarkivet_url(url: str) -> bool:
    u = (url or "").lower()
    return "filmarkivet.se" in u


def resolve_media_url(url: str) -> str | None:
    if not is_filmarkivet_url(url):
        return None
    try:
        html = fetch_html(url, scrapfly_fallback=False)
    except Exception:
        return None
    jw = extract_jw_file(html)
    if jw and ".mp4" in jw.lower():
        return jw
    # Fallback: prefer filmarkivet-eu S3 objects.
    s3 = [u for u in extract_mp4s(html) if "filmarkivet-eu" in u.lower()]
    return s3[-1] if s3 else None
