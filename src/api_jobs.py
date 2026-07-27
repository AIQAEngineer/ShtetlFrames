"""GET /api/jobs, /api/errors."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import ParseResult, parse_qs

from api_http import json_response
from db import get_job, list_jobs


def handle_get_jobs(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    # Do not call init_db() here — it takes the write lock and was stalling the
    # UI poll path whenever Pathé workers were also writing queue rows.
    json_response(handler, 200, {"jobs": list_jobs()})


def handle_get_job(handler: BaseHTTPRequestHandler, job_id: str) -> None:
    json_response(handler, 200, {"job": get_job(job_id)})


def handle_get_errors(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    from logutil import recent_errors

    qs = parse_qs(parsed.query)
    limit = int((qs.get("limit") or ["50"])[0] or 50)
    json_response(handler, 200, {"errors": recent_errors(limit=min(limit, 200))})
