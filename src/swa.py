"""Szukaj w Archiwach (szukajwarchiwach.gov.pl) photo discover + JPEG download.

The public search UI is Liferay/JS-heavy and often returns empty shells through
datacenter IPs. Autocomplete (`searchContentAuto`) returns JSON with obiekt /
jednostka / zespół hits including CDN image URLs on photos.szukajwarchiwach.gov.pl.
JPEGs are fetched through Scrapfly (ASP, country=pl).
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from config import OUTPUT_DIR, load_env

SWA_ORIGIN = "https://www.szukajwarchiwach.gov.pl"
PHOTOS_CDN = "https://photos.szukajwarchiwach.gov.pl"
SWA_IMAGES_DIR = OUTPUT_DIR / "swa_images"

# Keyword seeds for Orthodox / Jewish visual discovery (Polish archives).
DEFAULT_KEYWORDS = (
    "rabin",
    "synagoga",
    "Żyd",
    "Żydzi",
    "żydowski",
    "chasyd",
    "chasydzi",
    "ortodoks",
    "jarmułka",
    "pejsy",
    "sztetł",
    "sztetl",
    "bejs midrasz",
    "cheder",
    "kirkut",
    "cadyk",
    "rebe",
    "Hasid",
    "Jew",
    "Jewish",
)

OnStatus = Callable[[str], None] | None


def _scrapfly_key() -> str:
    load_env()
    return (os.environ.get("SCRAPFLY_API_KEY") or "").strip()


def _scrapfly_request(
    url: str,
    *,
    method: str = "GET",
    body: str | None = None,
    country: str = "pl",
    timeout: float = 120.0,
    referer: str | None = None,
    session: str | None = None,
) -> dict[str, Any]:
    key = _scrapfly_key()
    if not key:
        raise RuntimeError("SCRAPFLY_API_KEY required for szukajwarchiwach.gov.pl")
    params: dict[str, str] = {
        "key": key,
        "url": url,
        "asp": "true",
        "country": (country or "pl").strip().lower() or "pl",
    }
    if method.upper() != "GET":
        params["method"] = method.upper()
    if body is not None:
        params["body"] = body
        params["headers[content-type]"] = "application/x-www-form-urlencoded"
    if referer:
        params["headers[referer]"] = referer
    if session:
        params["session"] = session
    api = "https://api.scrapfly.io/scrape?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(api, headers={"User-Agent": "ShtetlFrames/1.0 (swa)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        raise RuntimeError(f"scrapfly_swa_http_{e.code}: {body}") from e
    result = data.get("result") or {}
    if not result.get("success"):
        raise RuntimeError(f"scrapfly_swa: {result.get('error') or result.get('reason') or data}")
    return result


def photo_url_max(url: str) -> str:
    """Upgrade CDN thumbnail (_mid/_min) to full (_max)."""
    u = (url or "").strip()
    if not u:
        return u
    if re.search(r"_(mid|min|thumb)$", u, flags=re.I):
        return re.sub(r"_(mid|min|thumb)$", "_max", u, flags=re.I)
    # Bare hash without size suffix — request max.
    if re.search(r"photos\.szukajwarchiwach\.gov\.pl/[a-f0-9]{32,}$", u, re.I):
        return u + "_max"
    return u


def absolutize_swa(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return SWA_ORIGIN + u
    return u


def plik_jpeg_url(plik_id: str | int) -> str:
    return f"{SWA_ORIGIN}/o/pliki-api/pliki/pobierzplikjpeg/{int(plik_id)}"


def autocomplete_search(
    query: str,
    *,
    photos_only: bool = True,
    country: str = "pl",
) -> list[dict[str, Any]]:
    """Return autocomplete hits (zespol / jednostka / obiekt) for ``query``."""
    q = (query or "").strip()
    if not q:
        return []
    endpoint = (
        f"{SWA_ORIGIN}/en/wyszukiwarka?"
        + urllib.parse.urlencode(
            {
                "p_p_id": "Wyszukiwarka",
                "p_p_lifecycle": "2",
                "p_p_state": "normal",
                "p_p_mode": "view",
                "p_p_resource_id": "searchContentAuto",
                "p_p_cacheability": "cacheLevelPage",
                "_Wyszukiwarka_q": q,
            }
        )
    )
    form = {
        "_Wyszukiwarka_searchKey": q,
        "_Wyszukiwarka_images": "true" if photos_only else "false",
        "_Wyszukiwarka_photos": "true" if photos_only else "false",
        "_Wyszukiwarka_acts": "false",
        "_Wyszukiwarka_posters": "false",
        "_Wyszukiwarka_projects": "false",
        "_Wyszukiwarka_sounds": "false",
        "_Wyszukiwarka_maps": "false",
        "_Wyszukiwarka_cmd": "autoComplete",
    }
    result = _scrapfly_request(
        endpoint,
        method="POST",
        body=urllib.parse.urlencode(form),
        country=country,
    )
    status = int(result.get("status_code") or 0)
    raw = result.get("content") or ""
    if status >= 400 or not raw:
        raise RuntimeError(f"swa_autocomplete_http_{status}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"swa_autocomplete_bad_json: {raw[:120]}") from e
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type") or "").lower()
        if typ in ("header",):
            continue
        out.append(item)
    return out


def hit_to_queue_row(item: dict[str, Any], *, query: str = "") -> dict[str, str] | None:
    """Map an autocomplete hit to a queue_items row (image URL preferred)."""
    typ = str(item.get("type") or "").lower()
    title = (item.get("title") or "").strip() or "SWA"
    page = absolutize_swa(str(item.get("url") or ""))
    image = (item.get("image") or "").strip()
    if image:
        image = photo_url_max(absolutize_swa(image))
    # Prefer direct CDN image when present (obiekt / some zespół covers).
    if image and "photos.szukajwarchiwach.gov.pl" in image:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", title)[:40].strip("_").lower() or "hit"
        return {
            "url": image,
            "title": f"[SWA] {title}"[:300],
            "year": str(item.get("okresPowstania") or "")[:40],
            "source": f"swa:{typ or 'photo'}",
            "downloadable": "yes",
            "hub_url": page or query,
            "_page_url": page,
            "_query": query,
            "_slug": slug,
        }
    # Unit / fond without image — queue the page for later scan extraction.
    if page and typ in ("jednostka", "zespol", "obiekt"):
        return {
            "url": page,
            "title": f"[SWA] {title}"[:300],
            "year": str(item.get("okresPowstania") or "")[:40],
            "source": f"swa:{typ}",
            "downloadable": "yes",
            "hub_url": page,
            "_page_url": page,
            "_query": query,
        }
    return None


def discover_keywords(
    keywords: list[str] | None = None,
    *,
    photos_only: bool = True,
    max_per_query: int = 40,
    on_status: OnStatus = None,
) -> list[dict[str, str]]:
    """Run autocomplete for each keyword; return deduped queue rows with image URLs."""
    terms = [t.strip() for t in (keywords or list(DEFAULT_KEYWORDS)) if t and t.strip()]
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for i, term in enumerate(terms, 1):
        if on_status:
            on_status(f"SWA search {i}/{len(terms)}: {term}")
        try:
            hits = autocomplete_search(term, photos_only=photos_only)
        except Exception as e:
            if on_status:
                on_status(f"SWA search failed ({term}): {e}"[:160])
            time.sleep(0.4)
            continue
        n = 0
        term_l = term.casefold()
        # Prefer title match, then obiekt (photo items), then pages we can resolve.
        def _rank(h: dict) -> tuple:
            title = str(h.get("title") or "").casefold()
            typ = str(h.get("type") or "").lower()
            title_hit = 0 if term_l and term_l in title else 1
            typ_rank = {"obiekt": 0, "jednostka": 1, "seria": 2, "zespol": 3}.get(typ, 4)
            has_img = 0 if (h.get("image") or "").strip() else 1
            return (title_hit, typ_rank, has_img)

        ordered = sorted(hits, key=_rank)
        for hit in ordered:
            row = hit_to_queue_row(hit, query=term)
            if not row:
                continue
            url = row["url"]
            if url in seen:
                continue
            title_l = (row.get("title") or "").casefold()
            is_cdn = "photos.szukajwarchiwach.gov.pl" in url or "/o/pliki-api/" in url
            is_page = "/jednostka/" in url or "/obiekt/" in url
            # Prefer CDN images; also queue jednostka/obiekt pages when title matches.
            if not is_cdn:
                if not (is_page and term_l and term_l in title_l):
                    continue
            seen.add(url)
            rows.append(row)
            n += 1
            if n >= max_per_query:
                break
        time.sleep(0.35)
    return rows


# --- Full-text paginated search (Liferay Result portlet) ---------------------
#
# The Result portlet keeps search state server-side per HTTP session, so all
# requests for one query share a Scrapfly ``session``. The search action works
# as plain GET (same as the tag links); pagination is ``_Result_cur`` +
# ``_Result_delta`` render params on the wyszukiwarka page.

_FULL_SEARCH_ACTION = (
    f"{SWA_ORIGIN}/en/wyszukiwarka?"
    "p_p_id=Wyszukiwarka&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view"
    "&_Wyszukiwarka_javax.portlet.action=redirectToSearch"
)
_FULL_SEARCH_PAGE = (
    f"{SWA_ORIGIN}/en/wyszukiwarka?"
    "p_p_id=Result&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
)


def _full_search_get(url: str, session: str) -> str:
    """GET through Scrapfly with retries (ASP intermittently 422s on sessions)."""
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            result = _scrapfly_request(url, country="pl", session=session)
            return str(result.get("content") or "")
        except Exception as e:
            last_err = e
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"swa_full_search_failed: {last_err}")


def parse_full_results(html: str) -> list[dict[str, str]]:
    """Parse Result portlet HTML into {page, title, year, image} items."""
    items: list[dict[str, str]] = []
    for block in re.split(r'class="row search-result"', html or "")[1:]:
        m = re.search(r'href="(/(?:jednostka|obiekt|zespol)/-/[^"#]+)(?:#[^"]*)?"', block)
        if not m:
            continue
        t = re.search(r'<a class="found"[^>]*>(.*?)</a>', block, re.S)
        title = re.sub(r"<[^>]+>", "", t.group(1)).strip() if t else ""
        title = re.sub(r"\s+", " ", title)
        y = re.search(
            r'year / years:\s*</dt>\s*<dd>\s*<p class="found">(.*?)</p>', block, re.S
        )
        year = re.sub(r"<[^>]+>", "", y.group(1)).strip() if y else ""
        img = re.search(
            r"photos\.szukajwarchiwach\.gov\.pl/[a-f0-9]+(?:_(?:mid|min|max))?",
            block,
            re.I,
        )
        items.append(
            {
                "page": m.group(1),
                "title": title,
                "year": year[:40],
                "image": img.group(0) if img else "",
            }
        )
    return items


def full_search(
    query: str,
    *,
    max_pages: int = 5,
    delta: int = 200,
    session: str = "",
    on_status: OnStatus = None,
) -> list[dict[str, str]]:
    """Paginated full-text search; returns deduped items across pages."""
    q = (query or "").strip()
    if not q:
        return []
    sess = session or f"swa_full_{os.getpid()}_{abs(hash(q)) % 99999}"
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for cur in range(1, max(1, int(max_pages)) + 1):
        if cur == 1:
            url = _FULL_SEARCH_ACTION + "&" + urllib.parse.urlencode(
                {
                    "_Wyszukiwarka_keywords": q,
                    "_Wyszukiwarka_images": "true",
                    "_Wyszukiwarka_filters": "photos",
                }
            )
        else:
            url = _FULL_SEARCH_PAGE + "&" + urllib.parse.urlencode(
                {
                    "_Result_resetCur": "false",
                    "_Result_delta": str(delta),
                    "_Result_cur": str(cur),
                }
            )
        if on_status:
            on_status(f"SWA full search '{q}' page {cur}/{max_pages}")
        html = _full_search_get(url, sess)
        items = parse_full_results(html)
        new = 0
        for it in items:
            if it["page"] not in seen:
                seen.add(it["page"])
                out.append(it)
                new += 1
        if not items or (cur > 1 and new == 0):
            break
        time.sleep(0.4)
    return out


def full_result_to_queue_row(item: dict[str, str], *, query: str = "") -> dict[str, str] | None:
    """Map a full-search item to a queue row (page URL — scrape expands scans)."""
    page = absolutize_swa(item.get("page") or "")
    if not page:
        return None
    kind = "jednostka"
    for k in ("obiekt", "zespol"):
        if f"/{k}/" in page:
            kind = k
            break
    title = (item.get("title") or "").strip() or "SWA"
    return {
        "url": page,
        "title": f"[SWA] {title}"[:300],
        "year": (item.get("year") or "")[:40],
        "source": f"swa:full:{kind}",
        "downloadable": "yes",
        "hub_url": page,
        "_page_url": page,
        "_query": query,
    }


def discover_keywords_full(
    keywords: list[str] | None = None,
    *,
    max_pages: int = 5,
    max_per_query: int = 200,
    on_status: OnStatus = None,
) -> list[dict[str, str]]:
    """Full-text paginated search per keyword; deduped queue rows of page URLs."""
    terms = [t.strip() for t in (keywords or list(DEFAULT_KEYWORDS)) if t and t.strip()]
    run_session = f"swa_full_{os.getpid()}_{int(time.time()) % 100000}"
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for i, term in enumerate(terms, 1):
        if on_status:
            on_status(f"SWA full {i}/{len(terms)}: {term}")
        try:
            items = full_search(
                term,
                max_pages=max_pages,
                session=run_session,
                on_status=on_status,
            )
        except Exception as e:
            if on_status:
                on_status(f"SWA full search failed ({term}): {e}"[:160])
            time.sleep(0.5)
            continue
        n = 0
        for item in items:
            row = full_result_to_queue_row(item, query=term)
            if not row or row["url"] in seen:
                continue
            seen.add(row["url"])
            rows.append(row)
            n += 1
            if n >= max_per_query:
                break
        time.sleep(0.4)
    return rows


def extract_plik_ids_from_html(html: str) -> list[str]:
    ids = re.findall(r'data-plikid=["\']?(\d+)', html or "", flags=re.I)
    ids += re.findall(r"pobierzplikjpeg/(\d+)", html or "", flags=re.I)
    # Preserve order, unique.
    out: list[str] = []
    seen: set[str] = set()
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def extract_photo_cdn_urls(html: str) -> list[str]:
    found = re.findall(
        r"https?://photos\.szukajwarchiwach\.gov\.pl/[a-f0-9]+(?:_(?:mid|min|max))?",
        html or "",
        flags=re.I,
    )
    out: list[str] = []
    seen: set[str] = set()
    for u in found:
        u = photo_url_max(u)
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def resolve_page_images(page_url: str, *, on_status: OnStatus = None) -> list[str]:
    """Best-effort: fetch a jednostka/obiekt page and collect scan/CDN image URLs."""
    url = absolutize_swa(page_url)
    if not url:
        return []
    if on_status:
        on_status(f"resolve page… {url[-60:]}")
    try:
        from britishpathe import scrapfly_fetch_html

        html = scrapfly_fetch_html(url, render_js=True, rendering_wait=6000, country="pl") or ""
    except Exception:
        try:
            result = _scrapfly_request(url, country="pl")
            html = str(result.get("content") or "")
        except Exception:
            return []
    urls = extract_photo_cdn_urls(html)
    for plik in extract_plik_ids_from_html(html):
        urls.append(plik_jpeg_url(plik))
    # Dedup
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def download_image(
    url: str,
    dest: Path,
    *,
    country: str = "pl",
) -> Path:
    """Download a SWA JPEG (CDN or pliki-api) via Scrapfly into ``dest``."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    candidates = [url]
    # Prefer smaller mid first when max is requested — more reliable through ASP.
    if url.endswith("_max"):
        candidates = [url[:-4] + "_mid", url]
    elif url.endswith("_mid"):
        candidates = [url, url[:-4] + "_max"]
    last_err: Exception | None = None
    raw: bytes | None = None
    # Try each size variant a couple times — Scrapfly intermittently returns 422.
    attempts: list[str] = []
    for candidate in candidates:
        attempts.extend([candidate, candidate])
    for attempt, candidate in enumerate(attempts):
        if attempt:
            time.sleep(0.8 + 0.6 * (attempt % 2))
        try:
            result = _scrapfly_request(
                candidate,
                country=country,
                timeout=180.0,
                referer=f"{SWA_ORIGIN}/",
            )
            status = int(result.get("status_code") or 0)
            headers = result.get("response_headers") or {}
            ctype = str(
                headers.get("content-type") or headers.get("Content-Type") or ""
            ).lower()
            content = result.get("content") or ""
            if status >= 400 or not content:
                raise RuntimeError(f"swa_download_http_{status}")
            if isinstance(content, (bytes, bytearray)):
                raw = bytes(content)
            else:
                text = str(content)
                if text.startswith("\xff\xd8") or text.startswith("\x89PNG"):
                    raw = text.encode("latin-1")
                else:
                    raw = base64.b64decode(text, validate=False)
            if len(raw) < 200 or raw[:3] not in (b"\xff\xd8\xff", b"\x89PN"):
                if b"<html" in raw[:200].lower() or ctype.startswith("text/html"):
                    raise RuntimeError("swa_download_got_html")
                if raw[:3] != b"\xff\xd8\xff":
                    raise RuntimeError(f"swa_download_not_jpeg ct={ctype} n={len(raw)}")
            break
        except Exception as e:
            last_err = e
            raw = None
            continue
    if raw is None:
        raise RuntimeError(f"swa_download_failed: {last_err}")
    dest.write_bytes(raw)
    return dest


def slug_from_url(url: str) -> str:
    u = url or ""
    m = re.search(r"photos\.szukajwarchiwach\.gov\.pl/([a-f0-9]+)", u, re.I)
    if m:
        return m.group(1)[:24]
    m = re.search(r"pobierzplikjpeg/(\d+)", u, re.I)
    if m:
        return f"plik_{m.group(1)}"
    m = re.search(r"jednostka/(\d+)", u, re.I)
    if m:
        return f"jed_{m.group(1)}"
    return re.sub(r"[^a-zA-Z0-9]+", "_", u)[-40:].strip("_") or "swa"
