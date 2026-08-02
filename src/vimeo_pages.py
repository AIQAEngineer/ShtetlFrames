"""Generic Vimeo-embed page resolvers for EFG linked_out hosts.

Several archive sites only expose playable media as a player.vimeo.com iframe.
Return the player URL; download_entry passes the page as Referer and yt-dlp
--impersonate fetches it (do not set Origin — that 401s Vimeo).
"""

from __future__ import annotations

import html as htmlmod

from provider_html import extract_vimeo, fetch_html

# Substring match against the page URL (lowercased).
# digit.wdr.de embeds exist but are domain-locked (player 401 even with
# curl_cffi); leave them out so we don't fill the queue with hard failures.
_VIMEO_PAGE_HOSTS = (
    "kinoteka.org.rs",
    "efg1914filmoteca.com",
    "patrimonio.aamod.it",
    "aamod.it",
)


def is_vimeo_page_url(url: str) -> bool:
    u = (url or "").lower()
    return any(h in u for h in _VIMEO_PAGE_HOSTS)


def resolve_media_url(url: str) -> str | None:
    if not is_vimeo_page_url(url):
        return None
    page = htmlmod.unescape(url or "")
    try:
        html = fetch_html(page, scrapfly_fallback=False)
    except Exception:
        return None
    return extract_vimeo(html)
