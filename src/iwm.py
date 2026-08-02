"""IWM (iwm.org.uk) media resolver.

Imperial War Museums collection pages sit behind Cloudflare's anti-bot
challenge, so plain yt-dlp gets HTTP 403. Scrapfly ASP (no JS render needed)
passes it, and the returned HTML embeds the asset's MP4 on Rackspace Cloud
Files CDN in three endpoint variants (r97.stream / iosr / ssl). We prefer the
HTTPS `ssl.cf3.rackcdn.com` variant.

Resolved CDN URLs are long-lived signed assets, but resolve just-in-time at
download anyway — each resolve costs one Scrapfly credit.
"""

from __future__ import annotations

import re

_MP4_RE = re.compile(r'https?://[^\s"\'<>]+?\.mp4(?:\?[^\s"\'<>]*)?', re.I)


def is_iwm_url(url: str) -> bool:
    u = (url or "").lower()
    return "iwm.org.uk" in u and "/collections/item/" in u


def _rank(url: str) -> int:
    u = url.lower()
    if u.startswith("https") and "ssl.cf3.rackcdn.com" in u:
        return 0
    if u.startswith("https"):
        return 1
    return 2


def resolve_media_url(url: str) -> str | None:
    """Map an IWM collections item URL to a direct MP4 URL (or None)."""
    if not is_iwm_url(url):
        return None
    html = ""
    # Plain HTTP often works now; Scrapfly only if Cloudflare challenges us.
    try:
        from provider_html import fetch_html

        html = fetch_html(url, scrapfly_fallback=True)
    except Exception:
        try:
            from britishpathe import scrapfly_fetch_html

            html = scrapfly_fetch_html(url, render_js=True, rendering_wait=4000)
        except Exception:
            return None
    urls = sorted(set(_MP4_RE.findall(html)), key=_rank)
    return urls[0] if urls else None
