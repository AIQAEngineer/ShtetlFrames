"""Clip page: load Pathé video, cut start→end, upload to Google Drive."""

from __future__ import annotations

import re
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from api_http import json_response
from config import OUTPUT_DIR

TRIMS_DIR = OUTPUT_DIR / "trims"


def _resolve_pathe_video(body: dict) -> tuple[dict | None, dict | None]:
    from britishpathe import (
        asset_id_from_url,
        is_britishpathe_asset_url,
        normalize_asset_url,
    )
    from frame_strip import _download_source

    if not isinstance(body, dict):
        return None, {"ok": False, "error": "json_body_required"}

    raw_url = (body.get("url") or body.get("asset_url") or "").strip()
    video_id = (body.get("video_id") or "").strip()

    if raw_url:
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
        return {
            "url": url,
            "aid": str(aid),
            "video_id": video_id,
            "video": video,
        }, None

    if video_id:
        video = _find_local_video(video_id)
        if not video:
            return None, {"ok": False, "error": "video_not_found", "video_id": video_id}
        return {"url": None, "aid": None, "video_id": video_id, "video": video}, None

    return None, {"ok": False, "error": "url_or_video_id_required"}


def _find_local_video(video_id: str) -> Path | None:
    from config import VIDEOS_DIR

    if not VIDEOS_DIR.exists():
        return None
    exts = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".ogv"}
    for p in VIDEOS_DIR.iterdir():
        if p.stem == video_id and p.suffix.lower() in exts:
            return p
    for p in VIDEOS_DIR.iterdir():
        if video_id in p.stem and p.suffix.lower() in exts:
            return p
    return None


def _ffmpeg_bin() -> str:
    which = shutil.which("ffmpeg")
    if which:
        return which
    # Bundled with imageio-ffmpeg (already in this project's venv).
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).is_file():
            return bundled
    except Exception:
        pass
    # Common Windows installs
    for cand in (
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    ):
        if cand.is_file():
            return str(cand)
    return "ffmpeg"


def cut_clip(src: Path, start: float, end: float, *, stem: str) -> Path:
    """Cut ``[start, end)`` from ``src`` into ``output/trims/``."""
    if end <= start:
        raise ValueError("end_must_be_after_start")
    duration = max(0.05, float(end) - float(start))
    TRIMS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", stem)[:80] or "clip"
    out = TRIMS_DIR / f"{safe}_{start:.2f}-{end:.2f}.mp4"
    if out.is_file() and out.stat().st_size > 64:
        return out
    # Fast keyframe seek (-ss before -i), then accurate trim window.
    cmd = [
        _ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{float(start):.3f}",
        "-i",
        str(src),
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as e:
        raise RuntimeError("ffmpeg_not_found") from e
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "")[:400]
        raise RuntimeError(f"ffmpeg_failed: {err}") from e
    if not out.is_file() or out.stat().st_size < 64:
        raise RuntimeError("cut_empty")
    return out


def handle_get_drive_status(handler: BaseHTTPRequestHandler) -> None:
    import drive_upload

    json_response(handler, 200, drive_upload.status())


def handle_post_drive_auth(handler: BaseHTTPRequestHandler) -> None:
    import drive_upload

    try:
        st = drive_upload.authorize_oauth()
        json_response(handler, 200, {"ok": True, **st})
    except Exception as e:
        json_response(
            handler,
            400,
            {"ok": False, "error": "drive_auth_failed", "detail": str(e)[:400]},
        )


def handle_post_clip_load(handler: BaseHTTPRequestHandler, body: dict) -> None:
    ctx, err = _resolve_pathe_video(body)
    if err:
        code = 502 if err.get("error") == "download_failed" else 400
        json_response(handler, code, err)
        return
    assert ctx is not None
    video: Path = ctx["video"]
    json_response(
        handler,
        200,
        {
            "ok": True,
            "video_id": ctx["video_id"],
            "asset_id": ctx.get("aid"),
            "url": ctx.get("url"),
            "media_url": f"/media/video/{ctx['video_id']}",
            "bytes": video.stat().st_size,
            "name": video.name,
        },
    )


def handle_post_clip_cut(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from frame_strip import parse_mark_seconds

    ctx, err = _resolve_pathe_video(body)
    if err:
        code = 502 if err.get("error") == "download_failed" else 400
        json_response(handler, code, err)
        return
    assert ctx is not None

    start = parse_mark_seconds(body.get("start") if "start" in body else body.get("start_sec"))
    end = parse_mark_seconds(body.get("end") if "end" in body else body.get("end_sec"))
    if start is None or end is None:
        json_response(
            handler,
            400,
            {
                "ok": False,
                "error": "start_end_required",
                "hint": "Seconds as a number (e.g. 42.5) or m:ss",
            },
        )
        return
    if end <= start:
        json_response(handler, 400, {"ok": False, "error": "end_must_be_after_start"})
        return

    try:
        out = cut_clip(ctx["video"], start, end, stem=ctx["video_id"])
    except ValueError as e:
        json_response(handler, 400, {"ok": False, "error": str(e)})
        return
    except RuntimeError as e:
        msg = str(e)
        code = 500 if "ffmpeg_failed" in msg or "cut_empty" in msg else 503
        json_response(handler, code, {"ok": False, "error": msg})
        return

    json_response(
        handler,
        200,
        {
            "ok": True,
            "video_id": ctx["video_id"],
            "start_sec": start,
            "end_sec": end,
            "duration_sec": round(end - start, 3),
            "file": out.name,
            "bytes": out.stat().st_size,
            "media_url": f"/media/trim/{out.name}",
        },
    )


def handle_post_clip_upload(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """Cut (if needed) and upload to Google Drive."""
    import drive_upload
    from frame_strip import parse_mark_seconds

    if not isinstance(body, dict):
        json_response(handler, 400, {"ok": False, "error": "json_body_required"})
        return

    st = drive_upload.status()
    if not st.get("configured"):
        json_response(
            handler,
            400,
            {
                "ok": False,
                "error": "drive_not_configured",
                "hint": st.get("hint"),
                "drive": st,
            },
        )
        return

    trim_name = (body.get("file") or body.get("trim_file") or "").strip()
    out: Path | None = None
    start = parse_mark_seconds(body.get("start") if "start" in body else body.get("start_sec"))
    end = parse_mark_seconds(body.get("end") if "end" in body else body.get("end_sec"))

    if trim_name:
        safe = Path(trim_name).name
        cand = TRIMS_DIR / safe
        if cand.is_file():
            out = cand
        # else fall through and cut from source
    if out is None:
        ctx, err = _resolve_pathe_video(body)
        if err:
            code = 502 if err.get("error") == "download_failed" else 400
            json_response(handler, code, err)
            return
        assert ctx is not None
        if start is None or end is None:
            json_response(handler, 400, {"ok": False, "error": "start_end_required"})
            return
        if end <= start:
            json_response(handler, 400, {"ok": False, "error": "end_must_be_after_start"})
            return
        try:
            out = cut_clip(ctx["video"], start, end, stem=ctx["video_id"])
        except RuntimeError as e:
            json_response(handler, 500, {"ok": False, "error": str(e)})
            return

    assert out is not None
    name = (body.get("name") or body.get("title") or out.name).strip() or out.name
    try:
        meta = drive_upload.upload_file(out, name=name)
    except Exception as e:
        json_response(
            handler,
            502,
            {"ok": False, "error": "drive_upload_failed", "detail": str(e)[:400]},
        )
        return

    json_response(
        handler,
        200,
        {
            "ok": True,
            "file": out.name,
            "bytes": out.stat().st_size,
            "media_url": f"/media/trim/{out.name}",
            "start_sec": start,
            "end_sec": end,
            "drive": meta,
        },
    )
