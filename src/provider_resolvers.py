"""Provider media resolvers: item page URL -> direct playable media URL.

Hosts where yt-dlp is broken or blocked and we carry a custom resolver:
- euscreen.eu (item.html)  -> src/euscreen.py  (LouServlet setVideo protocol)
- iwm.org.uk (collections) -> src/iwm.py       (Scrapfly past Cloudflare, rackcdn MP4)

Used just-in-time by download_entry (local) and process_video_remote (RunPod),
so queue rows keep their canonical item-page URLs and tickets never go stale.
"""

from __future__ import annotations


def needs_resolve(url: str) -> bool:
    from euscreen import is_euscreen_url
    from iwm import is_iwm_url

    return is_euscreen_url(url) or is_iwm_url(url)


def resolve_media_url(url: str) -> str | None:
    from euscreen import is_euscreen_url
    from euscreen import resolve_media_url as euscreen_resolve
    from iwm import is_iwm_url
    from iwm import resolve_media_url as iwm_resolve

    if is_euscreen_url(url):
        return euscreen_resolve(url)
    if is_iwm_url(url):
        return iwm_resolve(url)
    return None
