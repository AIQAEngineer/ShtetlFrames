"""Filmhíradók Online (filmhiradokonline.hu) — Hungarian newsreel catalog + resolver.

The site hosts ~23k newsreel *segments* (1910s–1940s, Magyar Világhíradó,
Kino Riport, Az Est Film…). Each segment has a watch page (`watch.php?id=N`);
the player iframe (`player.php?id=N`) exposes the full-issue MP4 plus the
segment's start/end seconds inside it:

    <source src="https://filmhiradokonline.hu/fo/mvh-0412.mp4">
    var start = 82; var end = 143;

The MP4 403s without a same-site Referer. The full catalog paginates through
`search.php?page=N&q=` (10 items/page; empty query = everything, newest first).
"""

from __future__ import annotations

import html as _html
import re
import threading
import time
from typing import Any, Callable, Iterator
from urllib.parse import urljoin

import requests

ORIGIN = "https://filmhiradokonline.hu"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ShtetlFrames/1.0 (research; respectful archival use)"
PER_PAGE = 10

_tls = threading.local()

_WATCH_RE = re.compile(r"(?:^|/)watch\.php\?[^\"']*?\bid=(\d+)|(?:^|/)player\.php\?[^\"']*?\bid=(\d+)", re.I)
_ITEM_RE = re.compile(r'<div class="search_item(?:\s+last)?">(.*?)(?=<div class="search_item(?:\s+last)?">|<div class="pager_container")', re.S)
_ITEM_IMG_RE = re.compile(r'getimage\.php\?src=([^&"\']+)', re.I)
_ITEM_DATE_RE = re.compile(r'<span class="date"><strong>([^<]+)</strong>,\s*([^<]*)</span>', re.I)
_ITEM_TITLE_RE = re.compile(r'<span class="title"><a href="(watch\.php\?id=\d+)">(.*?)</a></span>', re.S)
_ITEM_VIEWS_RE = re.compile(r"<strong>(\d+)</strong>\s*megtekint", re.I)
_TOTAL_RE = re.compile(r"sszesen\s*<strong>\s*([\d\s]+)\s*</strong>|sszesen\s+([\d\s]+)\s+tal", re.I)
_SOURCE_RE = re.compile(r'<source[^>]+src=["\']([^"\']+\.mp4[^"\']*)["\']', re.I)
_START_RE = re.compile(r"var\s+start\s*=\s*(\d+)", re.I)
_END_RE = re.compile(r"var\s+end\s*=\s*(\d+)", re.I)
_POSTER_RE = re.compile(r'poster=["\']([^"\']+)["\']', re.I)
_YEAR_RE = re.compile(r"(\d{4})")

# Short-lived cache so resolve_media_url + the segment/section lookup in
# process_video_remote share one player.php fetch.
_seg_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_SEG_CACHE_TTL = 600.0

OnStatus = Callable[[str], None] | None


def _session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _tls.session = s
    return s


def _get(url: str, *, timeout: int = 30) -> str:
    r = _session().get(url, timeout=timeout)
    r.raise_for_status()
    r.encoding = "utf-8"  # site declares UTF-8; requests may guess latin-1
    return r.text


def is_filmhiradok_url(url: str) -> bool:
    return "filmhiradokonline.hu" in (url or "").lower()


def watch_id(url: str) -> str | None:
    m = _WATCH_RE.search(url or "")
    if not m:
        return None
    return m.group(1) or m.group(2)


def watch_url(wid: str | int) -> str:
    return f"{ORIGIN}/watch.php?id={wid}"


def resolve_segment(url: str) -> dict[str, Any] | None:
    """watch/player page → full-issue MP4 + segment window (cached ~10 min)."""
    wid = watch_id(url)
    if not wid:
        return None
    now = time.time()
    hit = _seg_cache.get(wid)
    if hit and now - hit[0] < _SEG_CACHE_TTL:
        return dict(hit[1])
    try:
        html = _get(f"{ORIGIN}/player.php?id={wid}")
    except Exception:
        return None
    m = _SOURCE_RE.search(html or "")
    if not m:
        return None
    mp4 = urljoin(ORIGIN, _html.unescape(m.group(1)))
    start = _START_RE.search(html or "")
    end = _END_RE.search(html or "")
    poster = _POSTER_RE.search(html or "")
    seg: dict[str, Any] = {
        "id": wid,
        "watch_url": watch_url(wid),
        "mp4": mp4,
        "start": int(start.group(1)) if start else None,
        "end": int(end.group(1)) if end else None,
        "poster": poster.group(1) if poster else "",
        "referer": watch_url(wid),
    }
    _seg_cache[wid] = (now, seg)
    return dict(seg)


def resolve_media_url(url: str) -> str | None:
    """provider_resolvers interface: item page → direct playable MP4."""
    if not is_filmhiradok_url(url):
        return None
    seg = resolve_segment(url)
    return seg["mp4"] if seg else None


def _parse_item(block: str) -> dict[str, Any] | None:
    t = _ITEM_TITLE_RE.search(block)
    if not t:
        return None
    href = _html.unescape(t.group(1))
    title = _html.unescape(re.sub(r"\s+", " ", t.group(2) or "")).strip()
    wid = watch_id(href)
    if not wid:
        return None
    date = ""
    series = ""
    d = _ITEM_DATE_RE.search(block)
    if d:
        date = _html.unescape(d.group(1) or "").strip()
        series = _html.unescape(re.sub(r"\s+", " ", d.group(2) or "")).strip()
    year = ""
    y = _YEAR_RE.search(date)
    if y:
        year = y.group(1)
    thumb = ""
    i = _ITEM_IMG_RE.search(block)
    if i:
        thumb = f"{ORIGIN}/getimage.php?src={i.group(1)}&size=small"
    views = 0
    v = _ITEM_VIEWS_RE.search(block)
    if v:
        views = int(v.group(1))
    return {
        "url": watch_url(wid),
        "id": wid,
        "title": title or f"filmhiradok {wid}",
        "date": date,
        "series": series,
        "year": year,
        "thumb": thumb,
        "views": views,
    }


def parse_search_page(html: str) -> tuple[list[dict[str, Any]], int]:
    """One search.php results page → (items, catalog total)."""
    items: list[dict[str, Any]] = []
    for m in _ITEM_RE.finditer(html or ""):
        it = _parse_item(m.group(1))
        if it:
            items.append(it)
    total = 0
    tm = _TOTAL_RE.search(html or "")
    if tm:
        raw = (tm.group(1) or tm.group(2) or "").replace(" ", "").replace("\xa0", "")
        if raw.isdigit():
            total = int(raw)
    return items, total


def catalog_pages(total: int) -> int:
    return max(1, (total + PER_PAGE - 1) // PER_PAGE)


def fetch_search_page(page: int, query: str = "") -> tuple[list[dict[str, Any]], int]:
    """Fetch one search.php results page → (items, catalog total)."""
    from urllib.parse import quote

    url = f"{ORIGIN}/search.php?page={max(0, int(page))}&q={quote((query or '').strip())}"
    try:
        html = _get(url)
    except Exception:
        time.sleep(1.5)
        html = _get(url)  # one retry after a short pause
    return parse_search_page(html)


def iter_catalog(
    *,
    query: str = "",
    max_pages: int = 0,
    delay: float = 0.35,
    on_status: OnStatus = None,
) -> Iterator[dict[str, Any]]:
    """Yield catalog items (newest first). query='' = full catalog; max_pages=0 = all."""
    from urllib.parse import quote

    q = (query or "").strip()
    page = 0
    total = 0
    n_pages = 1
    while page < n_pages:
        url = f"{ORIGIN}/search.php?page={page}&q={quote(q)}"
        try:
            html = _get(url)
        except Exception as e:
            if on_status:
                on_status(f"page {page + 1} fetch failed ({e}) — retrying once…")
            time.sleep(1.5)
            html = _get(url)
        items, total_found = parse_search_page(html)
        if total_found:
            total = total_found
            n_pages = catalog_pages(total)
            if max_pages > 0:
                n_pages = min(n_pages, max_pages)
        if on_status:
            on_status(
                f"page {page + 1}/{n_pages} · {len(items)} items · catalog {total or '?'}"
            )
        for it in items:
            yield it
        page += 1
        if not items:
            # Past the end or an empty result set — stop instead of spinning.
            break
        if page < n_pages:
            time.sleep(max(0.0, delay))
