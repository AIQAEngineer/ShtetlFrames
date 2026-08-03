"""SWA (szukajwarchiwach.gov.pl) still-image APIs."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import ParseResult, parse_qs

from api_http import json_response
from config import QUEUE_PAGE_SIZE, effective_scan_backend
from db import clear_queue, get_job, init_db, list_queue_page, queue_stats
from swa import DEFAULT_KEYWORDS


def handle_get_summary(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    from pipeline_swa import scrape_live_snapshot

    init_db()
    json_response(
        handler,
        200,
        {
            "queue": queue_stats("swa"),
            "discover": get_job("swa_discover"),
            "scrape": get_job("swa_scrape"),
            "live": scrape_live_snapshot(),
            "keywords": list(DEFAULT_KEYWORDS),
            "backend": "local-images",
            "scan_backend": effective_scan_backend(),
        },
    )


def handle_get_queue(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    qs = parse_qs(parsed.query)
    offset = int((qs.get("offset") or ["0"])[0] or 0)
    limit = int((qs.get("limit") or [str(QUEUE_PAGE_SIZE)])[0] or QUEUE_PAGE_SIZE)
    status = (qs.get("status") or [""])[0].strip()
    q = (qs.get("q") or [""])[0].strip()
    page = list_queue_page(offset=offset, limit=limit, status=status, q=q, source="swa")
    json_response(handler, 200, {**queue_stats("swa"), **page})


def handle_post_discover(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_swa import start_discover

    body = body if isinstance(body, dict) else {}
    keywords = body.get("keywords")
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.replace(";", ",").split(",") if k.strip()]
    elif isinstance(keywords, list):
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
    else:
        keywords = None
    try:
        max_per = int(body.get("max_per_query") or 40)
    except (TypeError, ValueError):
        max_per = 40
    mode = str(body.get("mode") or "autocomplete").strip().lower()
    if mode not in ("autocomplete", "full"):
        mode = "autocomplete"
    try:
        max_pages = int(body.get("max_pages") or 5)
    except (TypeError, ValueError):
        max_pages = 5
    result = start_discover(
        keywords=keywords, max_per_query=max_per, mode=mode, max_pages=max_pages
    )
    code = 200 if result.get("ok") else 409
    json_response(handler, code, result)


def handle_post_scrape(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_swa import start_scrape

    body = body if isinstance(body, dict) else {}
    result = start_scrape(
        max_images=body.get("max_images", body.get("max_videos", "all")),
        workers=body.get("workers", 4),
    )
    code = 200 if result.get("ok") else 409
    json_response(handler, code, {**result, "job": get_job("swa_scrape")})


def handle_post_scrape_stop(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_swa import stop_scrape

    body = body if isinstance(body, dict) else {}
    result = stop_scrape(message=str(body.get("message") or "stopped by user"))
    json_response(handler, 200, {**result, "job": get_job("swa_scrape")})


def handle_post_queue_clear(handler: BaseHTTPRequestHandler, body: dict) -> None:
    init_db()
    n = clear_queue("swa")
    json_response(handler, 200, {"ok": True, "deleted": n, **queue_stats("swa")})
