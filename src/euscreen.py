"""EUScreen (euscreen.eu) media resolver.

yt-dlp's built-in EUScreen extractor is broken against the current site — its
`setVideo\\(({.+})\\)` regex is greedy and over-captures when the LouServlet JS
contains later `)($end$)put` segments (JSONDecodeError "Extra data"). The site
itself is a noterik "LOU" app; the item page is a 4KB shell that bootstraps
/eddie/js/eddie.js, which talks to LouServlet:

1. POST capabilities XML -> LouServlet returns a <screenid> for this session.
2. POST that document back (screenid -> screenId) -> full JS application state
   (~2MB), containing `setVideo({...})($end$)put` with progressive MP4 sources
   on stream*.noterik.com (ticketed URLs).

We replicate the two POSTs with plain requests (no Scrapfly needed) and parse
setVideo with a non-greedy match. Resolved URLs carry a `?ticket=` and may
expire — resolve just-in-time at download, not at queue import.
"""

from __future__ import annotations

import json
import re
import threading

import requests

SERVLET = "https://euscreen.eu/lou/LouServlet/domain/euscreenxl/html5application/euscreenxlitem"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ShtetlFrames/1.0 (euscreen)"

_PAYLOAD = (
    b"<fsxml><screen><properties><screenId>-1</screenId></properties>"
    b'<capabilities id="1"><properties><platform>Win32</platform>'
    b"<appcodename>Mozilla</appcodename><appname>Netscape</appname>"
    b"<appversion>5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    b"(KHTML, like Gecko) Chrome/120.0 Safari/537.36</appversion>"
    b"<useragent>Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    b"(KHTML, like Gecko) Chrome/120.0 Safari/537.36</useragent>"
    b"<cookiesenabled>true</cookiesenabled><screenwidth>1280</screenwidth>"
    b"<screenheight>800</screenheight><orientation>undefined</orientation>"
    b"</properties></capabilities></screen></fsxml>"
)

_ID_RE = re.compile(r"[?&]id=(EUS_[A-Za-z0-9]+)")
# Non-greedy is the whole fix vs yt-dlp's extractor (see module docstring).
_SET_VIDEO_RE = re.compile(r"setVideo\((\{.+?\})\)\(\$end\$\)put", re.S)
_KEY_FIX_RE = re.compile(r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")

_tls = threading.local()


def is_euscreen_url(url: str) -> bool:
    return "euscreen.eu" in (url or "").lower() and "item.html" in (url or "").lower()


def extract_id(url: str) -> str | None:
    m = _ID_RE.search(url or "")
    return m.group(1) if m else None


def _session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Content-Type": "text/xml; charset=utf-8"})
        _tls.session = s
    return s


def resolve_media_url(url: str, *, timeout: int = 40) -> str | None:
    """Map an EUScreen item.html URL to a direct progressive MP4 URL (or None)."""
    vid = extract_id(url)
    if not vid:
        return None
    s = _session()
    try:
        r1 = s.post(SERVLET, params={"actionlist": "itempage", "id": vid}, data=_PAYLOAD, timeout=timeout)
        r1.raise_for_status()
        r2 = s.post(SERVLET, data=r1.text.replace("screenid", "screenId").encode(), timeout=timeout)
        r2.raise_for_status()
    except Exception:
        return None
    m = _SET_VIDEO_RE.search(r2.text)
    if not m:
        return None
    raw = _KEY_FIX_RE.sub(r'\1"\2":', m.group(1)).replace("'", '"')
    try:
        data = json.loads(raw)
    except Exception:
        return None
    sources = data.get("sources") or []
    best: str | None = None
    for src in sources:
        u = (src.get("src") or "").strip()
        if not u.startswith("http"):
            continue
        if ".mp4" in u.lower():
            best = u
            break
        if best is None:
            best = u
    return best
