"""Offline EFG resolve rewrite — dead CDN → YouTube / no_media (no Scrapfly)."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from config import DATA_DIR, OUTPUT_DIR

JSONL = DATA_DIR / "efg" / "resolve_pre1950.jsonl"
CSV_OUT = OUTPUT_DIR / "efg_discovery_pre1950.csv"

DEAD = ("videocinecitta.bytewise.it", "bytewise.it", "repozytorium.fn.org.pl", "fn.org.pl")
_YT_RE = re.compile(
    r'(?:www\.)?(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=)|youtu\.be/)'
    r'([A-Za-z0-9_-]{6,})',
    re.I,
)

CSV_FIELDS = [
    "record_id", "provider_prefix", "title", "year", "genre", "provider_name",
    "kind", "stream_url", "external_url", "external_host", "shown_at",
    "shown_at_name", "detail_url", "error", "query",
]


def _is_dead(url: str) -> bool:
    u = (url or "").lower()
    return any(d in u for d in DEAD)


def _yt(url: str) -> str | None:
    m = _YT_RE.search(url or "")
    if not m:
        return None
    return f"https://www.youtube.com/watch?v={m.group(1)}"


def rewrite_row(r: dict) -> tuple[dict, str | None]:
    kind = (r.get("kind") or "").lower()
    stream = r.get("stream_url") or ""
    if kind != "embedded" or not _is_dead(stream):
        return r, None
    yt = _yt(r.get("shown_at") or "") or _yt(stream)
    out = dict(r)
    if yt:
        out["kind"] = "youtube"
        out["dead_embed"] = stream
        out["stream_url"] = yt
        out.pop("error", None)
        return out, "dead->youtube"
    out["kind"] = "no_media"
    out["dead_embed"] = stream
    out["error"] = "dead_embed_only"
    out.pop("stream_url", None)
    return out, "dead->no_media"


def run_rewrite() -> dict:
    """Rewrite JSONL + CSV. Returns change/kind counters. Raises if JSONL missing."""
    if not JSONL.exists():
        raise FileNotFoundError(f"missing {JSONL}")

    rows: list[dict] = []
    changes: Counter[str] = Counter()
    for line in JSONL.open(encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        r2, label = rewrite_row(r)
        if label:
            changes[label] += 1
        rows.append(r2)

    tmp = JSONL.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(JSONL)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = {k: r.get(k, "") for k in CSV_FIELDS}
            if not row.get("detail_url") and r.get("detail_path"):
                row["detail_url"] = "https://www.europeanfilmgateway.eu" + r["detail_path"]
            if not row.get("external_host") and row.get("external_url"):
                row["external_host"] = urlparse(row["external_url"]).netloc
            w.writerow(row)

    kinds = Counter((r.get("kind") or "?") for r in rows)
    return {
        "changes": dict(changes),
        "kinds": dict(kinds),
        "rows": len(rows),
        "csv": str(CSV_OUT),
    }
