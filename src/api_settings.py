"""HTTP handlers for /api/settings (extracted from serve.py)."""

from __future__ import annotations

import config as app_config
from api_http import json_response
from config import effective_scan_backend, load_env, runpod_configured
from settings_store import set_settings, settings_public_view


def handle_get_settings(handler) -> None:
    load_env()
    json_response(handler, 200, settings_public_view())


def handle_post_settings(handler, body) -> None:
    try:
        values = set_settings(body if isinstance(body, dict) else {})
    except ValueError as e:
        json_response(handler, 400, {"ok": False, "error": str(e)})
        return
    load_env()
    json_response(
        handler,
        200,
        {
            "ok": True,
            **settings_public_view(values),
            "scan": {
                "backend": effective_scan_backend(),
                "requested": app_config.SCAN_BACKEND,
                "runpod_configured": runpod_configured(),
                "image_set": bool(app_config.RUNPOD_DOCKER_IMAGE),
                "pod_id": (app_config.RUNPOD_POD_ID or "")[:12],
                "gpu_type": app_config.RUNPOD_GPU_TYPE,
                "max_inflight": app_config.RUNPOD_MAX_INFLIGHT,
                "stop_when_done": app_config.RUNPOD_STOP_WHEN_DONE,
            },
        },
    )
