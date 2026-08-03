"""Filmhíradók Online (filmhiradokonline.hu) APIs — discover, scrape, queue."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import ParseResult, parse_qs

from api_http import json_response
from config import QUEUE_PAGE_SIZE, effective_scan_backend
from db import clear_queue, get_job, init_db, list_queue_page, queue_stats


def handle_get_summary(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    from pipeline_scrape import scrape_live_snapshot

    init_db()
    json_response(
        handler,
        200,
        {
            "queue": queue_stats("fho"),
            "discover": get_job("fho_discover"),
            "scrape": get_job("scrape"),
            "live": scrape_live_snapshot(),
            "backend": effective_scan_backend(),
        },
    )


def handle_get_queue(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    qs = parse_qs(parsed.query)
    offset = int((qs.get("offset") or ["0"])[0] or 0)
    limit = int((qs.get("limit") or [str(QUEUE_PAGE_SIZE)])[0] or QUEUE_PAGE_SIZE)
    status = (qs.get("status") or [""])[0].strip()
    q = (qs.get("q") or [""])[0].strip()
    page = list_queue_page(offset=offset, limit=limit, status=status, q=q, source="fho")
    json_response(handler, 200, {**queue_stats("fho"), **page})


def handle_post_discover(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_filmhiradok import start_discover

    body = body if isinstance(body, dict) else {}
    query = str(body.get("query") or "").strip()
    try:
        max_pages = int(body.get("max_pages") or 0)
    except (TypeError, ValueError):
        max_pages = 0
    result = start_discover(query=query, max_pages=max(0, max_pages))
    code = 200 if result.get("ok") else 409
    json_response(handler, code, result)


def handle_post_discover_stop(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_filmhiradok import stop_discover

    result = stop_discover()
    json_response(handler, 200, {**result, "job": get_job("fho_discover")})


def handle_post_scrape(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_filmhiradok import start_scrape

    body = body if isinstance(body, dict) else {}
    result = start_scrape(
        max_videos=body.get("max_videos", "all"),
        workers=body.get("workers", 2),
    )
    code = 200 if result.get("ok") else 409
    json_response(handler, code, result)


def handle_post_scrape_stop(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_filmhiradok import stop_scrape

    body = body if isinstance(body, dict) else {}
    result = stop_scrape(message=str(body.get("message") or "Filmhíradók scrape stopped"))
    json_response(handler, 200, {**result, "job": get_job("scrape")})


def handle_post_queue_clear(handler: BaseHTTPRequestHandler, body: dict) -> None:
    init_db()
    n = clear_queue("fho")
    json_response(handler, 200, {"ok": True, "deleted": n, **queue_stats("fho")})
