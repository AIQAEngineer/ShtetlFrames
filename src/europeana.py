"""Europeana source: Record API search for pre-1950 video.

Europeana (europeana.eu) aggregates cultural-heritage objects from thousands
of European institutions. Its Record API supports a `TYPE:VIDEO` filter and a
`YEAR` date facet, so we can enumerate moving-image records dated before 1950
across the whole network (a superset of EFG's ~40 archives).

Requires a free Europeana API key in env: EUROPEANA_API_KEY (or EUROPEANA_KEY).
Register at https://pro.europeana.eu/page/apis#authentication

Notes:
- Pagination is cursor-based (`cursorMark`) for deep result sets; `*` to start.
- We filter by YEAR ranges via `qf=YEAR:[x TO y]` per-decade and page within
  each decade, which keeps result sets small enough to page fully.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.europeana.eu/record/v2/search.json"

# Decades strictly before 1950 as YEAR range filters.
PRE1950_YEAR_RANGES = (
    (1890, 1899), (1900, 1909), (1910, 1919),
    (1920, 1929), (1930, 1939), (1940, 1949),
)

# Decades through 1980 (inclusive) as YEAR range filters.
THROUGH1980_YEAR_RANGES = PRE1950_YEAR_RANGES + (
    (1950, 1959), (1960, 1969), (1970, 1980),
)

ROWS_PER_PAGE = 100  # API max is 100


def _api_key() -> str:
    try:
        from config import load_env  # type: ignore
        load_env()
    except Exception:
        pass
    return (os.environ.get("EUROPEANA_API_KEY") or os.environ.get("EUROPEANA_KEY") or "").strip()


def search(
    query: str = "*:*",
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    cursor: str = "*",
    rows: int = ROWS_PER_PAGE,
    timeout: int = 60,
) -> dict:
    """One search page. Returns the parsed JSON response dict."""
    key = _api_key()
    if not key:
        raise RuntimeError("EUROPEANA_API_KEY required for Europeana API")
    params: dict[str, str] = {
        "wskey": key,
        "query": query,
        "rows": str(min(rows, ROWS_PER_PAGE)),
        "cursor": cursor,
        "qf": "TYPE:VIDEO",
        "profile": "standard",
    }
    if year_from is not None and year_to is not None:
        params["qf"] = f"TYPE:VIDEO AND YEAR:[{year_from} TO {year_to}]"
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ShtetlFrames/1.0 (europeana)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        if int(e.code or 0) == 429:
            raise RuntimeError("europeana_http_429") from e
        raise RuntimeError(f"europeana_http_{e.code}: {body}") from e
    if not data.get("success"):
        raise RuntimeError(f"europeana_api: {str(data.get('error') or data)[:200]}")
    return data


def parse_items(data: dict) -> tuple[list[dict], str | None]:
    """Extract records + next cursorMark from a search response."""
    out: list[dict] = []
    for it in data.get("items") or []:
        rid = it.get("id") or ""
        title = ""
        t = it.get("title")
        if isinstance(t, list) and t:
            title = t[0]
        elif isinstance(t, str):
            title = t
        year = None
        y = it.get("year")
        if isinstance(y, list) and y:
            try:
                year = int(str(y[0])[:4])
            except Exception:
                year = None
        edm = it.get("edmIsShownAt")
        if isinstance(edm, list):
            edm = edm[0] if edm else ""
        provider = it.get("dataProvider")
        if isinstance(provider, list):
            provider = provider[0] if provider else ""
        out.append({
            "record_id": rid,
            "title": title,
            "year": year,
            "provider_name": provider or "",
            "edm_is_shown_at": edm or "",
            "europeana_url": ("https://www.europeana.eu/item" + rid) if rid else "",
            "rights": (it.get("rights") or [""])[0] if it.get("rights") else "",
            "type": it.get("type") or "",
        })
    return out, data.get("nextCursor")


def total_results(data: dict) -> int:
    try:
        return int(data.get("totalResults") or 0)
    except Exception:
        return 0


def year_range_totals(*, sleep_s: float = 0.4) -> list[tuple[str, int]]:
    """Return [(range_label, total_video_hits)] for each pre-1950 decade."""
    out: list[tuple[str, int]] = []
    for y0, y1 in PRE1950_YEAR_RANGES:
        d = search("*:*", year_from=y0, year_to=y1, rows=1)
        out.append((f"{y0}-{y1}", total_results(d)))
        time.sleep(sleep_s)
    return out
