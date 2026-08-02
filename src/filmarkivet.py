"""Filmarkivet.se resolver — JW Player playlist → S3 MP4."""

from __future__ import annotations

import re

from provider_fetch import fetch_html, head_ok

_FILE_RE = re.compile(r'file:\s*"(https://s3[^"]+\.mp4)"', re.I)


def is_filmarkivet_url(url: str) -> bool:
    u = (url or "").lower()
    return "filmarkivet.se" in u and "/movies/" in u


def resolve_media_url(url: str) -> str | None:
    if not is_filmarkivet_url(url):
        return None
    html = fetch_html(url)
    if not html:
        return None
    candidates: list[str] = []
    for m in _FILE_RE.finditer(html):
        line_start = html.rfind("\n", 0, m.start()) + 1
        line = html[line_start : m.start()].lstrip()
        # Skip JS comments: //file: "..."
        if line.startswith("//"):
            continue
        candidates.append(m.group(1))
    for cand in candidates:
        if head_ok(cand):
            return cand
    return candidates[0] if candidates else None
