"""Shared HTML fetch + media URL extraction for provider resolvers.

Prefer plain HTTP (no Scrapfly credits). Fall back to Scrapfly ASP only when
the host blocks or returns a challenge page.
"""

from __future__ import annotations

import html as _html
import re
import threading
from urllib.parse import urljoin, urlparse

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ShtetlFrames/1.0 (provider)"
_tls = threading.local()

_MP4_RE = re.compile(r'https?://[^\s"\'<>]+?\.mp4(?:\?[^\s"\'<>]*)?', re.I)
_M3U8_RE = re.compile(r'https?://[^\s"\'<>]+?\.m3u8(?:\?[^\s"\'<>]*)?', re.I)
_YT_EMBED_RE = re.compile(
    r'(?:www\.)?(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=)|youtu\.be/)'
    r'([A-Za-z0-9_-]{6,})',
    re.I,
)
_VIMEO_RE = re.compile(r'(?:player\.)?vimeo\.com/(?:video/)?(\d+)', re.I)
# JWPlayer / similar: active `file: "..."` (skip //file commented lines).
_JW_FILE_RE = re.compile(r'(?m)^[ \t]*file:\s*["\'](https?://[^"\']+)["\']')


def _session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _tls.session = s
    return s


def fetch_html(url: str, *, timeout: int = 30, scrapfly_fallback: bool = True) -> str:
    """Fetch page HTML. Plain requests first; optional Scrapfly fallback."""
    try:
        r = _session().get(url, timeout=timeout, allow_redirects=True)
        if r.status_code < 400 and len(r.text or "") > 800:
            return r.text
    except Exception:
        pass
    if not scrapfly_fallback:
        raise RuntimeError(f"provider_fetch_failed: {url[:120]}")
    from britishpathe import scrapfly_fetch_html

    try:
        return scrapfly_fetch_html(url, render_js=False)
    except Exception:
        return scrapfly_fetch_html(url, render_js=True, rendering_wait=4000)


def absolutize(base: str, href: str) -> str:
    return urljoin(base, _html.unescape(href or "").strip())


def extract_mp4s(html: str) -> list[str]:
    return list(dict.fromkeys(_MP4_RE.findall(html or "")))


def extract_m3u8s(html: str) -> list[str]:
    # Strip trailing backslash artifacts from JSON-escaped HTML.
    out: list[str] = []
    for u in _M3U8_RE.findall(html or ""):
        u = u.rstrip("\\").rstrip("\\'")
        if u not in out:
            out.append(u)
    return out


def extract_youtube(html: str) -> str | None:
    m = _YT_EMBED_RE.search(html or "")
    if not m:
        return None
    return f"https://www.youtube.com/watch?v={m.group(1)}"


def extract_vimeo(html: str) -> str | None:
    # Pages often JSON-escape slashes (https:\/\/player.vimeo.com\/video\/123).
    text = _html.unescape(html or "").replace("\\/", "/")
    m = _VIMEO_RE.search(text)
    if not m:
        return None
    # Prefer the embed player URL — many EFG-linked clips are private on
    # vimeo.com/<id> (404) but playable via player.vimeo.com/video/<id>.
    return f"https://player.vimeo.com/video/{m.group(1)}"


def _fetch_vimeo_player_html(player: str, *, referer: str | None, timeout: int) -> str | None:
    """Fetch player.vimeo.com HTML. Prefer curl_cffi (TLS fingerprint); plain HTTP 401s."""
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            from curl_cffi import requests as creq

            r = creq.get(player, impersonate="chrome", headers=headers, timeout=timeout)
            if r.status_code < 400 and len(r.text or "") > 500:
                return r.text
        except Exception as e:
            last_err = e
        try:
            r = _session().get(player, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code < 400 and len(r.text or "") > 500:
                return r.text
        except Exception as e:
            last_err = e
        if attempt < 2:
            import time

            time.sleep(0.4 * (attempt + 1))
    _ = last_err
    return None


def resolve_vimeo_progressive(vimeo_url: str, *, referer: str | None = None, timeout: int = 30) -> str | None:
    """Map a Vimeo page/player URL to a progressive CDN MP4 (or None).

    Private/embed-only clips 404 on vimeo.com/<id> but expose signed progressive
    sources inside player.vimeo.com/video/<id> when fetched with the host referer
    and a Chrome TLS fingerprint (curl_cffi).
    """
    m = _VIMEO_RE.search((vimeo_url or "").replace("\\/", "/"))
    if not m:
        return None
    vid = m.group(1)
    player = f"https://player.vimeo.com/video/{vid}"
    html = _fetch_vimeo_player_html(player, referer=referer, timeout=timeout)
    if not html:
        return None
    # Prefer progressive MP4s from the inline player config.
    mp4s = extract_mp4s(html)
    # Prefer higher quality when multiple (URLs often differ by file id; last is usually better).
    good = [u for u in mp4s if "vimeocdn.com" in u.lower() or "vimeo" in u.lower()]
    if good:
        # Pick tallest when height is in the query/path; else last progressive.
        def _rank(u: str) -> tuple[int, int]:
            hm = re.search(r"[^\d](\d{3,4})p[^\d]", u)
            h = int(hm.group(1)) if hm else 0
            return (h, len(u))

        return sorted(good, key=_rank)[-1]
    return None


def extract_jw_file(html: str) -> str | None:
    """Active JWPlayer `file:` URL (ignores //file comments)."""
    hits = _JW_FILE_RE.findall(html or "")
    return hits[0] if hits else None


def host_of(url: str) -> str:
    return (urlparse(url or "").netloc or "").lower()
