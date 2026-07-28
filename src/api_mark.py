"""Pathé mark peek: URL + second → pick frames → multi-frame HQ combine."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api_http import json_response


def _resolve_pathe_video(body: dict) -> tuple[dict | None, dict | None]:
    """Return (ctx, error_payload). ctx has url, aid, video."""
    from britishpathe import (
        asset_id_from_url,
        is_britishpathe_asset_url,
        normalize_asset_url,
    )
    from frame_strip import _download_source

    if not isinstance(body, dict):
        return None, {"ok": False, "error": "json_body_required"}

    raw_url = (body.get("url") or body.get("asset_url") or "").strip()
    if not raw_url:
        return None, {"ok": False, "error": "url_required"}
    if not is_britishpathe_asset_url(raw_url):
        return None, {
            "ok": False,
            "error": "britishpathe_asset_url_required",
            "hint": "Paste a URL like https://www.britishpathe.com/asset/187521/",
        }

    url = normalize_asset_url(raw_url)
    aid = asset_id_from_url(url)
    if not aid:
        return None, {"ok": False, "error": "asset_id_parse_failed"}

    video_id = f"pathe_{aid}"
    video = _download_source(url, video_id, video_id)
    if not video:
        return None, {
            "ok": False,
            "error": "download_failed",
            "asset_id": aid,
            "url": url,
        }
    return {"url": url, "aid": str(aid), "video": video}, None


def handle_post_mark(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from frame_strip import build_mark_triplet, parse_mark_seconds

    ctx, err = _resolve_pathe_video(body)
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

    ctx, err = _resolve_pathe_video(body)
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
