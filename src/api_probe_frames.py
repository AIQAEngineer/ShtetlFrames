"""API for reviewing/including deep-sampled CLIP Keep/Pass frames."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import ParseResult, parse_qs

from api_http import json_response


def handle_get_frames(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    from clip_ft import list_dataset_frames

    qs = parse_qs(parsed.query)
    label = (qs.get("label") or [""])[0].strip().lower() or None
    if label == "all":
        label = None
    status = (qs.get("status") or ["all"])[0].strip().lower()
    included = None
    if status in ("in", "included", "include"):
        included = True
    elif status in ("out", "excluded", "exclude"):
        included = False
    try:
        limit = int((qs.get("limit") or ["400"])[0])
    except ValueError:
        limit = 400
    try:
        offset = int((qs.get("offset") or ["0"])[0])
    except ValueError:
        offset = 0
    json_response(
        handler,
        200,
        list_dataset_frames(
            label=label, included=included, limit=limit, offset=offset
        ),
    )


def handle_get_summary(handler: BaseHTTPRequestHandler) -> None:
    from clip_ft import list_dataset_frames, load_exclusions, exclusions_path

    data = list_dataset_frames(limit=1, offset=0)
    json_response(
        handler,
        200,
        {
            "ok": True,
            "counts": data.get("counts"),
            "total": data.get("total"),
            "n_excluded": len(load_exclusions()),
            "exclusions_path": str(exclusions_path()),
        },
    )


def handle_post_exclude(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from clip_ft import list_dataset_frames, set_excluded

    if not isinstance(body, dict):
        json_response(handler, 400, {"ok": False, "error": "json_body_required"})
        return

    excluded = body.get("excluded")
    if excluded is None:
        excluded = True
    excluded = bool(excluded)

    paths = body.get("paths") or body.get("path")
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list) or not paths:
        # Bulk by label filter
        label = (body.get("label") or "").strip().lower() or None
        if label == "all":
            label = None
        if label not in (None, "keep", "pass"):
            json_response(handler, 400, {"ok": False, "error": "paths_or_label_required"})
            return
        listing = list_dataset_frames(label=label, limit=5000, offset=0)
        paths = [i["path"] for i in listing.get("items") or []]

    result = set_excluded([str(p) for p in paths], excluded=excluded)
    summary = list_dataset_frames(limit=1, offset=0)
    result["counts"] = summary.get("counts")
    json_response(handler, 200, result)
