"""Local web server: discover → scrape → review (SQLite)."""

from __future__ import annotations

import importlib
import inspect
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from api_http import bytes_response, cors, file_response, json_response, parse_json_body
from config import CONTACT_DIR, OUTPUT_DIR, ROOT, VIDEOS_DIR, load_env
from db import init_db, reset_stale_jobs
from media_files import find_video_file

WEB_DIR = ROOT / "web"
PORT = 8787

# —— Page hubs (old single-purpose pages 302-redirect into these) ——
PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/review": "review.html",
    "/review.html": "review.html",
    "/train": "train.html",
    "/train.html": "train.html",
    "/tools": "tools.html",
    "/tools.html": "tools.html",
    "/pathe": "pathe.html",
    "/pathe.html": "pathe.html",
}

PAGE_REDIRECTS = {
    "/health": "/?tab=ops",
    "/health.html": "/?tab=ops",
    "/probe": "/train?tab=frames",
    "/probe.html": "/train?tab=frames",
    "/crops": "/review?tab=crops",
    "/crops.html": "/review?tab=crops",
    "/mark": "/tools?tab=mark",
    "/mark.html": "/tools?tab=mark",
    "/clip": "/tools?tab=clip",
    "/clip.html": "/tools?tab=clip",
}

# —— API route tables: path → "module:function" (lazy-imported once, cached) ——
GET_ROUTES = {
    "/api/summary": "api_summary:handle_get_summary",
    "/api/health": "api_health:handle_get_health",
    "/api/settings": "api_settings:handle_get_settings",
    "/api/runpod/build": "api_runpod:handle_get_build",
    "/api/runpod/go": "api_runpod:handle_get_go",
    "/api/runpod/pod": "api_runpod:handle_get_pod",
    "/api/queue": "api_queue:handle_get_queue",
    "/api/queue/items": "api_queue:handle_get_queue",
    "/api/pathe/summary": "api_pathe:handle_get_summary",
    "/api/pathe/queue": "api_pathe:handle_get_queue",
    "/api/train/summary": "api_train:handle_get_summary",
    "/api/train/clips": "api_train:handle_get_clips",
    "/api/train/youtube": "api_train:handle_get_youtube",
    "/api/clip_ft/frames": "api_probe_frames:handle_get_frames",
    "/api/clip_ft/summary": "api_probe_frames:handle_get_summary",
    "/api/errors": "api_jobs:handle_get_errors",
    "/api/jobs": "api_jobs:handle_get_jobs",
    "/api/candidates": "api_review:handle_get_candidates",
    "/api/stills/status": "api_review:handle_get_stills_status",
    "/api/review/label_stats": "api_review:handle_get_label_stats",
    "/api/crops": "api_crops:handle_get_crops",
    "/api/clip/drive": "api_clip:handle_get_drive_status",
}

# Static JSON hints for POST-only endpoints hit with GET.
GET_HINTS = {
    "/api/mark": "POST {url, mark} — Pathé asset URL + second mark; POST /api/mark/combine {url, times[]}",
    "/api/mark/combine": "POST {url, times[], mark?} — stitch selected frames side by side at full res",
    "/api/clip/drive/auth": "POST /api/clip/drive/auth — open browser to sign in with Google",
    "/api/clip": "POST /api/clip/load {url}; /api/clip/cut {url,start,end}; /api/clip/upload {url,start,end}",
    "/api/clip/load": "POST /api/clip/load {url}; /api/clip/cut {url,start,end}; /api/clip/upload {url,start,end}",
    "/api/clip/cut": "POST /api/clip/load {url}; /api/clip/cut {url,start,end}; /api/clip/upload {url,start,end}",
    "/api/clip/upload": "POST /api/clip/load {url}; /api/clip/cut {url,start,end}; /api/clip/upload {url,start,end}",
}

POST_ROUTES = {
    "/api/youtube/cookies": "yt_cookies:handle_post_cookies",
    "/api/youtube/cookies/har": "yt_cookies:handle_post_cookies_har",
    "/api/settings": "api_settings:handle_post_settings",
    "/api/runpod/build": "api_runpod:handle_post_build",
    "/api/runpod/go": "api_runpod:handle_post_go",
    "/api/runpod/pod/start": "api_runpod:handle_post_pod_start",
    "/api/runpod/pod/stop": "api_runpod:handle_post_pod_stop",
    "/api/runpod/pod/reload": "api_runpod:handle_post_pod_reload",
    "/api/runpod/pool/sync": "api_runpod:handle_post_pool_sync",
    "/api/discover": "api_queue:handle_post_discover",
    "/api/pathe/discover": "api_pathe:handle_post_discover",
    "/api/pathe/scrape": "api_pathe:handle_post_scrape",
    "/api/pathe/scrape/stop": "api_pathe:handle_post_scrape_stop",
    "/api/train/seed": "api_train:handle_post_seed",
    "/api/train/youtube": "api_train:handle_post_youtube",
    "/api/train/clear": "api_train:handle_post_clear",
    "/api/train/label": "api_train:handle_post_label",
    "/api/train/thumbs": "api_train:handle_post_thumbs",
    "/api/train/scan": "api_train:handle_post_scan",
    "/api/train/clip": "api_train:handle_post_clip",
    "/api/clip_ft/exclude": "api_probe_frames:handle_post_exclude",
    "/api/console/refresh": "api_jobs:handle_post_console_refresh",
    "/api/pathe/queue/clear": "api_pathe:handle_post_queue_clear",
    "/api/queue/clear": "api_queue:handle_post_queue_clear",
    "/api/scrape": "api_queue:handle_post_scrape",
    "/api/queue/delete": "api_queue:handle_post_queue_delete",
    "/api/queue/priority": "api_queue:handle_post_queue_priority",
    "/api/crops": "api_crops:handle_post_crop",
    "/api/mark": "api_mark:handle_post_mark",
    "/api/mark/combine": "api_mark:handle_post_mark_combine",
    "/api/clip/load": "api_clip:handle_post_clip_load",
    "/api/clip/cut": "api_clip:handle_post_clip_cut",
    "/api/clip/upload": "api_clip:handle_post_clip_upload",
    "/api/clip/drive/auth": "api_clip:handle_post_drive_auth",
    "/api/review": "api_review:handle_post_review",
    "/api/stills/backfill": "api_review:handle_post_stills_backfill",
}

_modules: dict[str, object] = {}


def load_route_module(name: str):
    mod = _modules.get(name)
    if mod is None:
        mod = importlib.import_module(name)
        _modules[name] = mod
    return mod


def resolve_route(spec: str):
    """Resolve a "module:function" route spec to a callable (used by tests too)."""
    mod_name, func_name = spec.split(":", 1)
    return getattr(load_route_module(mod_name), func_name)


def call_route(func, handler, arg) -> None:
    """Dispatch to handlers that take (handler, arg) or just (handler)."""
    try:
        arity = len(inspect.signature(func).parameters)
    except (TypeError, ValueError):
        arity = 2
    if arity >= 2:
        func(handler, arg)
    else:
        func(handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        try:
            from console_dash import is_enabled

            if is_enabled():
                return
        except Exception:
            pass
        print(f"[web] {self.address_string()} {fmt % args}")

    def _cors(self) -> None:
        cors(self)

    def _json(self, code: int, payload: object) -> None:
        json_response(self, code, payload)

    def _bytes(self, code: int, data: bytes, content_type: str, *, no_cache: bool = False) -> None:
        bytes_response(self, code, data, content_type, no_cache=no_cache)

    def _file(self, path: Path, content_type: str | None = None) -> None:
        file_response(self, path, content_type)

    def _redirect(self, target: str, query: str = "") -> None:
        if query:
            target += ("&" if "?" in target else "?") + query
        self.send_response(302)
        self.send_header("Location", target)
        self._cors()
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        page = PAGES.get(path)
        if page:
            self._file(WEB_DIR / page, "text/html; charset=utf-8")
            return

        target = PAGE_REDIRECTS.get(path)
        if target:
            self._redirect(target, parsed.query)
            return

        if path.startswith("/assets/"):
            name = Path(path.split("/assets/", 1)[1]).name
            self._file(WEB_DIR / "assets" / name)
            return

        if path.startswith("/media/sheet/"):
            name = Path(path.split("/media/sheet/", 1)[1]).name
            sheet = CONTACT_DIR / name
            guessed = mimetypes.guess_type(name)[0] or "image/jpeg"
            self._file(sheet, guessed)
            return

        if path.startswith("/media/video/"):
            vid = path.split("/media/video/", 1)[1]
            vid = re.sub(r"[^\w.\-\[\] (),]", "", vid)
            f = find_video_file(VIDEOS_DIR, vid)
            if not f:
                self._json(404, {"error": "video not found", "video_id": vid})
                return
            ctype = mimetypes.guess_type(str(f))[0] or "video/mp4"
            self._file(f, ctype)
            return

        if path.startswith("/media/trim/"):
            name = Path(path.split("/media/trim/", 1)[1]).name
            trim = OUTPUT_DIR / "trims" / name
            if not trim.is_file():
                self._json(404, {"error": "trim not found", "file": name})
                return
            ctype = mimetypes.guess_type(name)[0] or "video/mp4"
            self._file(trim, ctype)
            return

        if path.startswith("/media/clip_ft/"):
            rel = path.split("/media/clip_ft/", 1)[1]
            rel = rel.replace("\\", "/").lstrip("/")
            parts = rel.split("/")
            if (
                len(parts) != 2
                or parts[0] not in ("keep", "pass")
                or ".." in rel
                or not parts[1].endswith((".jpg", ".jpeg", ".png", ".webp"))
            ):
                self._json(400, {"error": "bad clip_ft path"})
                return
            f = OUTPUT_DIR / "clip_ft" / "dataset" / parts[0] / parts[1]
            if not f.is_file():
                self._json(404, {"error": "frame not found", "path": rel})
                return
            ctype = mimetypes.guess_type(f.name)[0] or "image/jpeg"
            self._file(f, ctype)
            return

        if path.startswith("/api/jobs/"):
            jid = path.split("/api/jobs/", 1)[1].strip("/")
            api_jobs = load_route_module("api_jobs")
            api_jobs.handle_get_job(self, jid)
            return

        hint = GET_HINTS.get(path)
        if hint:
            self._json(200, {"ok": True, "hint": hint})
            return

        spec = GET_ROUTES.get(path)
        if spec:
            call_route(resolve_route(spec), self, parsed)
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = parse_json_body(self)
        if body is None:
            return

        spec = POST_ROUTES.get(path)
        if spec:
            call_route(
                resolve_route(spec),
                self,
                body if isinstance(body, dict) else {},
            )
            return

        self._json(404, {"error": "not found"})


def main() -> None:
    load_env()
    init_db()
    try:
        from settings_store import ensure_settings_table, get_all_settings, set_settings

        ensure_settings_table()
        # Seed SQLite from current environ/.env once so UI shows values
        current = get_all_settings()
        set_settings(current)
    except Exception:
        pass
    reset_stale_jobs()
    try:
        from logutil import _ensure

        _ensure()
    except Exception:
        pass
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    (WEB_DIR / "assets").mkdir(parents=True, exist_ok=True)
    CONTACT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from still_ensure import kick_backfill_missing_stills, start_ensure_worker

        start_ensure_worker()
        # Repair Review blanks left by truncated pod JSON / failed hydrate.
        kick_backfill_missing_stills(limit=5000)
    except Exception as e:
        print(f"[web] still backfill kick skipped: {e}"[:160])
    host = "127.0.0.1"
    server = ThreadingHTTPServer((host, PORT), Handler)
    try:
        from console_dash import enable, set_idle

        enable()
        set_idle(note="Browser should open on its own.")
    except Exception:
        print(f"ShtetlFrames -> http://{host}:{PORT}")
        print(f"Review workspace -> http://{host}:{PORT}/review")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        try:
            from console_dash import is_enabled, set_idle

            if is_enabled():
                set_idle(note="Stopped. You can close this window.")
            else:
                print("Stopped.")
        except Exception:
            print("Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
