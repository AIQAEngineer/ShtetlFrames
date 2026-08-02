"""NRK (tv.nrk.no) resolver via public psapi playback manifest → HLS."""

from __future__ import annotations

import re

import requests

from provider_fetch import UA

_ID_RE = re.compile(
    r"(?:/program/|/episode/|/FMAA|/AAAA|/MSUI|/NNFA|/KOID|/BUHA|/DABL|/DMPP)"
    r"|([A-Z]{4}\d{8})",
    re.I,
)
# Broader: last path segment that looks like NRK program id
_PROG_RE = re.compile(r"/([A-Z]{4}\d{8})(?:/|#|\?|$)", re.I)


def is_nrk_url(url: str) -> bool:
    u = (url or "").lower()
    return "tv.nrk.no" in u or "nrk.no/video" in u


def extract_program_id(url: str) -> str | None:
    u = url or ""
    m = _PROG_RE.search(u)
    if m:
        return m.group(1).upper()
    # fragment / query leftovers
    m2 = re.search(r"([A-Z]{4}\d{8})", u, re.I)
    return m2.group(1).upper() if m2 else None


def resolve_media_url(url: str, *, timeout: int = 25) -> str | None:
    if not is_nrk_url(url):
        return None
    pid = extract_program_id(url)
    if not pid:
        return None
    api = f"https://psapi.nrk.no/playback/manifest/program/{pid}"
    try:
        r = requests.get(
            api,
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    return _first_playable(data)


def _first_playable(obj) -> str | None:
    """Walk NRK JSON for the first HLS/mp4 playable URL."""
    found: list[str] = []

    def walk(o) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("url", "src", "href", "uri", "address") and isinstance(v, str):
                    if v.startswith("http") and (
                        ".m3u8" in v.lower() or ".mp4" in v.lower()
                    ):
                        found.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    m3 = [u for u in found if ".m3u8" in u.lower()]
    return (m3 or found)[0] if (m3 or found) else None
