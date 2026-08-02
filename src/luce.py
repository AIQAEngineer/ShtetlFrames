"""Archivio Luce (patrimonio.archivioluce.com) resolver.

Detail pages embed videocinecitta CDN URLs. Progressive .mp4 are often 404;
HLS ``…mp4/playlist.m3u8`` still answers 200 for many titles — prefer that.
"""

from __future__ import annotations

import re

from provider_fetch import fetch_html, find_m3u8s, find_mp4s, head_ok

_PLAYER_ID_RE = re.compile(r"/luce-web/videoplayer/([A-Za-z0-9]+)")


def is_luce_url(url: str) -> bool:
    u = (url or "").lower()
    return "patrimonio.archivioluce.com" in u or (
        "archivioluce.com" in u and "/detail/" in u
    )


def resolve_media_url(url: str) -> str | None:
    if not is_luce_url(url):
        return None
    # Bare homepage is not resolvable
    if re.fullmatch(r"https?://(www\.)?archivioluce\.com/?", (url or "").strip(), re.I):
        return None
    html = fetch_html(url)
    if not html:
        return None
    m3u8s = find_m3u8s(html)
    # Prefer playlists on the known CDN
    ranked = sorted(
        m3u8s,
        key=lambda u: (
            0 if "videocinecitta" in u.lower() else 1,
            0 if "playlist.m3u8" in u.lower() else 1,
            u,
        ),
    )
    for cand in ranked:
        if head_ok(cand):
            return cand
    if ranked:
        return ranked[0]
    # Last resort: progressive MP4 if any still live
    for mp4 in find_mp4s(html):
        if "videocinecitta" in mp4.lower() and head_ok(mp4):
            return mp4
    return None
