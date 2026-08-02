"""European Film Gateway (EFG) source: search listing + detail resolve.

EFG (europeanfilmgateway.eu) aggregates ~58k videos from 40+ European film
archives. Two record shapes exist on detail pages:

- Embedded media: a <video>/<source> tag with a direct MP4/HLS URL hosted by
  the contributing archive (e.g. cm:: / cinememoire.net). Downloadable as-is.
- Link-out records: no player, just an external link to the provider's own
  site (e.g. ina:: -> ina.fr). Those route through provider resolvers.

All EFG pages sit behind a `validate-browser` interstitial; Scrapfly (ASP,
render_js=False) passes it — see britishpathe.scrapfly_fetch_html.
"""

from __future__ import annotations

import base64
import html as _html_mod
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

EFG_BASE = "https://www.europeanfilmgateway.eu"

# Decades strictly before 1950 (EFG year facet values).
PRE1950_DECADES = (
    "1890-1899", "1900-1909", "1910-1919", "1920-1929", "1930-1939", "1940-1949",
)

_DETAIL_LINK_RE = re.compile(r'href="(/detail/((?:[^"/]+)/)?([a-z0-9]+::[a-f0-9]{16,}))"', re.I)
_SP_BLOCK_RE = re.compile(r'<div class="efg-sp">.*?(?=<div class="efg-sp">|<div class="view-footer|$)', re.S)
_SP_HREF_RE = re.compile(r'<a href="(/detail/[^"]+/([a-z0-9]+)::([a-f0-9]{16,}))"')
_SP_TITLE_RE = re.compile(r'<div class="efg-sp-headline">(.*?)</div>', re.S)
_SP_GENRE_RE = re.compile(r'<div class="efg-sp-infoline-genre">(.*?)</div>', re.S)
_SP_YEAR_RE = re.compile(r'<div class="efg-sp-infoline-productionYear">\s*(\d{4})\s*</div>')
_SP_PROVIDER_RE = re.compile(r'<div class="efg-sp-infoline-provider">(.*?)</div>', re.S)
_SP_THUMB_RE = re.compile(r'<img\s+src="([^"]+)"')
_SP_DESC_RE = re.compile(r'<div class="efg-sp-infoline-info-qtip-content">(.*?)</div>\s*</div>', re.S)
_PAGER_PAGE_RE = re.compile(r'href="\?page=(\d+)(?:%2C0)*%2C0%2C0"')

_VIDEO_SRC_RE = re.compile(r'<(?:video|source)[^>]*\ssrc="([^"]+)"', re.I)
_VIDEO_DATASETUP_RE = re.compile(r"<video[^>]*\sdata-setup='([^']+)'", re.I)
_SHOWN_AT_RE = re.compile(r'<div class="isShownAt">\s*<a href="([^"]+)"[^>]*>\s*View at ([^<]+)</a>', re.I)
_MP4_RE = re.compile(r'https?://[^"\'\s<>]+\.mp4(?:\?[^"\'\s<>]*)?', re.I)
_M3U8_RE = re.compile(r'https?://[^"\'\s<>]+\.m3u8(?:\?[^"\'\s<>]*)?', re.I)
_EXT_LINK_RE = re.compile(r'href="(https?://[^"]+)"')

# Domains we never treat as provider links.
_SKIP_DOMAINS = (
    "europeanfilmgateway.eu", "w3.org", "drupal.org", "europeana.eu",
    "facebook.com", "twitter.com", "google.com", "w3schools.com",
    "videojs.com",
)

# Provider domains routed to dedicated resolvers.
_INA_RE = re.compile(r'ina\.fr/(?:video|notice)/([A-Z0-9]{8,})', re.I)

# Static partner signature observed on ina.fr player config (partnerId=2).
# If it ever rotates, ina_resolve falls back to scraping the ina.fr page.
_INA_SIGN = "11c8b4d6087c3cd2fe18c341819398444b4653fb"


def _scrapfly_html(url: str) -> str:
    from britishpathe import scrapfly_fetch_html

    return scrapfly_fetch_html(url, render_js=False)


def _scrapfly_js_scenario(url: str, scenario: list[dict], *, rendering_wait: int = 3500) -> str:
    """Fetch ``url`` with Scrapfly JS rendering + a js_scenario (base64)."""
    from britishpathe import _note_scrapfly_429, _scrapfly_api_key, _wait_scrapfly_cooldown

    key = _scrapfly_api_key()
    if not key:
        raise RuntimeError("SCRAPFLY_API_KEY required for EFG pages")
    enc = base64.urlsafe_b64encode(
        json.dumps(scenario, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    qs = urllib.parse.urlencode({
        "key": key,
        "url": url,
        "asp": "true",
        "country": "us",
        "render_js": "true",
        "rendering_wait": str(max(0, int(rendering_wait))),
        "js_scenario": enc,
    })
    api = "https://api.scrapfly.io/scrape?" + qs
    _wait_scrapfly_cooldown()
    req = urllib.request.Request(api, headers={"User-Agent": "ShtetlFrames/1.0 (efg)"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if int(e.code or 0) == 429:
            ra = None
            try:
                ra = float(e.headers.get("Retry-After") or "")
            except Exception:
                ra = None
            _note_scrapfly_429(ra)
            raise RuntimeError("scrapfly_efg_http_429") from e
        raise
    result = data.get("result") or {}
    if not result.get("success"):
        err = result.get("error") or {}
        raise RuntimeError(f"scrapfly_efg: {err.get('message') or err or result}"[:200])
    return result.get("content") or ""


def fetch_filtered_search_page(
    query: str,
    page: int = 0,
    *,
    decades: tuple[str, ...] = PRE1950_DECADES,
    media: str = "video",
) -> str:
    """Load a search page with media+year filters applied via JS form submit.

    EFG filter state is not URL/cookie sticky across Scrapfly requests, so each
    page re-opens the unfiltered search and submits ``#searchFilter`` with
    ``form.action`` pointed at the desired page.
    """
    q = urllib.parse.quote(str(query).strip(), safe="")
    start = f"{EFG_BASE}/search-efg/{q}"
    page_path = f"/search-efg/{q}" + (f"?page={page}%2C0%2C0" if page else "")
    keep = {d: 1 for d in decades}
    keep_js = json.dumps(keep)
    script = (
        "var form=document.querySelector('#searchFilter');"
        "if(!form) return 'no-form';"
        f"var media={media!r};"
        "form.querySelectorAll('input[name=\"filter[media][]\"]').forEach(function(el){"
        "  el.checked=(el.value===media);"
        "});"
        f"var keep={keep_js};"
        "form.querySelectorAll('input[name=\"filter[year][]\"]').forEach(function(el){"
        "  el.checked=!!keep[el.value];"
        "});"
        f"form.action={page_path!r};"
        "form.submit(); return 'submitted';"
    )
    scenario = [
        {"wait": 1000},
        {"execute": {"script": script}},
        {"wait": 7000},
    ]
    return _scrapfly_js_scenario(start, scenario)


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return _html_mod.unescape(text).strip()


def search_url(query: str, page: int = 0) -> str:
    q = urllib.parse.quote(str(query).strip(), safe="")
    url = f"{EFG_BASE}/search-efg/{q}"
    if page > 0:
        url += f"?page={page}%2C0%2C0"
    return url


def parse_result_count(html: str) -> int | None:
    """Best-effort total hit count from a filtered results header."""
    m = re.search(r"\((\d[\d,]*) Results?\)", html)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except Exception:
        return None


def parse_search_page(html: str, query: str) -> tuple[list[dict], int]:
    """Parse one listing page. Returns (records, last_page_index)."""
    records: list[dict] = []
    for block in _SP_BLOCK_RE.findall(html):
        m = _SP_HREF_RE.search(block)
        if not m:
            continue
        path, prefix, rid = m.group(1), m.group(2).lower(), m.group(3)
        ym = _SP_YEAR_RE.search(block)
        records.append({
            "record_id": f"{prefix}::{rid}",
            "provider_prefix": prefix,
            "detail_path": path,
            "title": _clean(_SP_TITLE_RE.search(block).group(1)) if _SP_TITLE_RE.search(block) else "",
            "genre": _clean(_SP_GENRE_RE.search(block).group(1)) if _SP_GENRE_RE.search(block) else "",
            "year": int(ym.group(1)) if ym else None,
            "provider_name": _clean(_SP_PROVIDER_RE.search(block).group(1)) if _SP_PROVIDER_RE.search(block) else "",
            "thumb": (_SP_THUMB_RE.search(block).group(1) if _SP_THUMB_RE.search(block) else ""),
            "description": _clean(_SP_DESC_RE.search(block).group(1)) if _SP_DESC_RE.search(block) else "",
            "query": query,
        })
    last = 0
    pages = [int(p) for p in _PAGER_PAGE_RE.findall(html)]
    if pages:
        last = max(pages)
    return records, last


def parse_detail(html: str) -> dict:
    """Extract stream URLs and external provider links from a detail page."""
    streams: list[str] = []
    youtube: list[str] = []
    shown_at = ""
    shown_at_name = ""
    for m in _VIDEO_DATASETUP_RE.findall(html):
        try:
            setup = json.loads(_html_mod.unescape(m))
        except Exception:
            continue
        for src in (setup.get("sources") or []):
            u = (src.get("src") or "").strip()
            if not u:
                continue
            if "youtube" in (src.get("type") or "") or "youtu" in u:
                if u not in youtube:
                    youtube.append(u)
            elif u not in streams:
                streams.append(u)
    sm = _SHOWN_AT_RE.search(html)
    if sm:
        shown_at, shown_at_name = sm.group(1), sm.group(2).strip()
    for m in _VIDEO_SRC_RE.findall(html):
        if m.startswith("http") and m not in streams:
            streams.append(m)
    for rx in (_MP4_RE, _M3U8_RE):
        for m in rx.findall(html):
            if "w3schools.com" in m:
                continue
            if m not in streams:
                streams.append(m)
    external: list[str] = []
    for link in _EXT_LINK_RE.findall(html):
        host = urllib.parse.urlparse(link).netloc.lower()
        if any(d in host for d in _SKIP_DOMAINS):
            continue
        if link not in external:
            external.append(link)
    return {"streams": streams, "youtube": youtube, "external": external,
            "shown_at": shown_at, "shown_at_name": shown_at_name}


def ina_resolve(asset_id: str) -> dict | None:
    """Resolve an INA asset id to a direct media URL via the partner API.

    No Scrapfly needed — apipartner.ina.fr answers plain GETs with a Referer.
    Falls back to scraping the ina.fr page for a fresh `sign` if the static
    one is rejected.
    """
    def _call(sign: str) -> dict | None:
        api = f"https://apipartner.ina.fr/assets/{asset_id}?sign={sign}&partnerId=2"
        req = urllib.request.Request(
            api, headers={"Referer": "https://www.ina.fr/", "User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            return None

    data = _call(_INA_SIGN)
    if not data or not data.get("resourceUrl"):
        # Refresh the signature from the ina.fr page, then retry once.
        try:
            html = _scrapfly_html(f"https://www.ina.fr/video/{asset_id}")
            m = re.search(r"apipartner\.ina\.fr/assets/[A-Z0-9]+\?sign=([a-f0-9]{20,})", html)
            if m:
                data = _call(m.group(1))
        except Exception:
            pass
    if not data or not data.get("resourceUrl"):
        return None
    return {
        "stream_url": data["resourceUrl"],
        "duration": data.get("duration"),
        "broadcast_date": data.get("dateOfBroadcast"),
        "ina_title": data.get("title"),
        "ina_description": data.get("description"),
    }


def resolve_record(rec: dict) -> dict:
    """Resolve one listing record to a downloadable stream (when possible).

    Returns a dict with ``kind`` one of:
      embedded  – direct MP4/HLS on the EFG detail page
      youtube   – YouTube embed (downloadable via yt_dlp)
      ina       – resolved via apipartner.ina.fr (direct MP4)
      linked_out – only an external provider link exists (no resolver yet)
      no_media  – nothing playable found (often image/text records)
      error     – fetch/parse failure
    """
    out = dict(rec)
    url = EFG_BASE + rec["detail_path"]
    try:
        html = _scrapfly_html(url)
    except Exception as e:
        out.update(kind="error", error=str(e)[:160])
        return out

    info = parse_detail(html)
    if info.get("shown_at"):
        out["shown_at"] = info["shown_at"]
        out["shown_at_name"] = info["shown_at_name"]
    streams = [s for s in info["streams"] if s.lower().endswith(".mp4") or ".mp4?" in s.lower()]
    hls = [s for s in info["streams"] if ".m3u8" in s.lower()]

    if streams:
        out.update(kind="embedded", stream_url=streams[0])
        return out
    if hls:
        out.update(kind="embedded", stream_url=hls[0])
        return out
    if info["youtube"]:
        out.update(kind="youtube", stream_url=info["youtube"][0])
        return out

    for link in info["external"]:
        m = _INA_RE.search(link)
        if m:
            ina = ina_resolve(m.group(1))
            if ina:
                out.update(kind="ina", stream_url=ina["stream_url"],
                           ina_duration=ina.get("duration"))
                return out
            out.update(kind="linked_out", external_url=link, resolver="ina_failed")
            return out

    if info["external"]:
        out.update(kind="linked_out", external_url=info["external"][0],
                   external_host=urllib.parse.urlparse(info["external"][0]).netloc)
        return out
    out.update(kind="no_media")
    return out
