"""Shared helpers for provider page → media URL resolvers."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

_MP4_RE = re.compile(r'https?://[^\s"\'<>]+?\.mp4(?:\?[^\s"\'<>]*)?', re.I)
_M3U8_RE = re.compile(r'https?://[^\s"\'<>]+?\.m3u8(?:\?[^\s"\'<>]*)?', re.I)


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def fetch_html(url: str, *, timeout: int = 30, render_js: bool = False) -> str | None:
    """Plain GET first; optional Scrapfly when configured (Cloudflare / 403 hosts)."""
    try:
        r = requests.get(
            url,
            headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout,
            allow_redirects=True,
        )
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:
        pass
    try:
        from britishpathe import scrapfly_fetch_html

        return scrapfly_fetch_html(url, render_js=render_js, rendering_wait=4000 if render_js else 0)
    except Exception:
        return None


def find_mp4s(html: str) -> list[str]:
    return list(dict.fromkeys(_MP4_RE.findall(html or "")))


def find_m3u8s(html: str) -> list[str]:
    return list(dict.fromkeys(_M3U8_RE.findall(html or "")))


def prefer_media(urls: list[str], *, prefer_m3u8: bool = False) -> str | None:
    if not urls:
        return None
    https = [u for u in urls if u.lower().startswith("https://")]
    pool = https or urls
    if prefer_m3u8:
        m3 = [u for u in pool if ".m3u8" in u.lower()]
        if m3:
            return m3[0]
    mp4 = [u for u in pool if ".mp4" in u.lower() and ".m3u8" not in u.lower()]
    if mp4:
        return mp4[0]
    return pool[0]


def head_ok(url: str, *, timeout: int = 12) -> bool:
    try:
        r = requests.head(
            url,
            headers={"User-Agent": UA},
            timeout=timeout,
            allow_redirects=True,
        )
        if r.status_code in (200, 206):
            return True
        # Some CDNs reject HEAD — try ranged GET
        if r.status_code in (403, 405, 501):
            g = requests.get(
                url,
                headers={"User-Agent": UA, "Range": "bytes=0-1"},
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
            ok = g.status_code in (200, 206)
            g.close()
            return ok
    except Exception:
        return False
    return False
