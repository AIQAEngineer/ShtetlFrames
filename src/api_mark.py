"""Pathé mark peek: URL + second → pick frames → multi-frame HQ combine."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api_http import json_response
from frame_strip import resolve_pathe_video


def handle_post_mark(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from frame_strip import build_mark_triplet, parse_mark_seconds

    ctx, err = resolve_pathe_video(body, allow_video_id=False)
    if err:
        code = 502 if err.get("error") == "download_failed" else 400
        json_response(handler, code, err)
        return
    assert ctx is not None

    mark = parse_mark_seconds(body.get("mark") if "mark" in body else body.get("second"))
    if mark is None:
        json_response(
            handler,
            400,
            {
                "ok": False,
                "error": "mark_required",
                "hint": "Seconds as a number (e.g. 42.5) or m:ss",
            },
        )
        return

    result = build_mark_triplet(
        ctx["video"], mark, asset_id=ctx["aid"], source_url=ctx["url"]
    )
    if not result:
        json_response(
            handler,
            500,
            {"ok": False, "error": "extract_failed", "asset_id": ctx["aid"], "mark_sec": mark},
        )
        return

    json_response(handler, 200, {"ok": True, **result})


def handle_post_mark_combine(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from frame_strip import combine_mark_frames, parse_mark_seconds

    ctx, err = resolve_pathe_video(body, allow_video_id=False)
    if err:
        code = 502 if err.get("error") == "download_failed" else 400
        json_response(handler, code, err)
        return
    assert ctx is not None

    raw_times = body.get("times")
    if not isinstance(raw_times, list) or len(raw_times) < 2:
        json_response(
            handler,
            400,
            {
                "ok": False,
                "error": "times_required",
                "hint": "Select at least 2 frames (times: number[])",
            },
        )
        return

    mark = parse_mark_seconds(body.get("mark") if "mark" in body else body.get("second"))
    try:
        scale = int(body.get("scale") if body.get("scale") is not None else 1)
    except (TypeError, ValueError):
        scale = 1

    result = combine_mark_frames(
        ctx["video"],
        raw_times,
        asset_id=ctx["aid"],
        mark_sec=mark,
        source_url=ctx["url"],
        scale=scale,
    )
    if not result:
        json_response(
            handler,
            500,
            {
                "ok": False,
                "error": "combine_failed",
                "asset_id": ctx["aid"],
                "times": raw_times,
            },
        )
        return

    json_response(handler, 200, {"ok": True, **result})
