"""Elonet / Finna (elonet.finna.fi) resolver via Finna API → Icareus embed → HLS."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

import requests

from provider_fetch import UA, fetch_html, find_m3u8s

_RECORD_RE = re.compile(r"/Record/([^/?#]+)", re.I)
_ICAREUS_ID_RE = re.compile(r"players\.icareus\.com/[^/]+/embed/vod/(\d+)", re.I)


def is_elonet_url(url: str) -> bool:
    u = (url or "").lower()
    return "elonet.finna.fi" in u or "finna.fi/Record/" in u


def extract_record_id(url: str) -> str | None:
    m = _RECORD_RE.search(url or "")
    return unquote(m.group(1)) if m else None


def resolve_media_url(url: str, *, timeout: int = 30) -> str | None:
    if not is_elonet_url(url):
        return None
    rid = extract_record_id(url)
    if not rid:
        return None
    embed = _finna_embed_url(rid, timeout=timeout)
    if not embed:
        return None
    html = fetch_html(embed, timeout=timeout)
    if not html:
        return None
    # Strip trailing backslashes from Next.js-escaped URLs
    m3u8s = [u.rstrip("\\") for u in find_m3u8s(html)]
    if m3u8s:
        return m3u8s[0]
    m = _ICAREUS_ID_RE.search(embed)
    if m:
        # Known CloudFront pattern used by Icareus suite
        oid = "238613409"
        cand = (
            "https://d2ygzyc0kuitls.cloudfront.net/suitevodedge/_definst_/"
            f"smil/{m.group(1)}.smil/playlist.m3u8?organizationId={oid}"
        )
        return cand
    return None


def _finna_embed_url(record_id: str, *, timeout: int) -> str | None:
    try:
        r = requests.get(
            "https://api.finna.fi/v1/record",
            params={
                "id": record_id,
                "field[]": ["onlineUrls", "urls", "title"],
            },
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    records = data.get("records") or []
    if not records:
        return None
    rec = records[0]
    for key in ("onlineUrls", "urls"):
        for item in rec.get(key) or []:
            u = (item.get("url") or "").strip()
            if "icareus.com" in u.lower() or "embed" in u.lower():
                return u
            if u.startswith("http") and urlparse(u).path:
                # Prefer iframe embeds
                if item.get("embed") == "iframe":
                    return u
    return None
