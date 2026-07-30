"""Append-only structured error/event logging for scrapes and discovers."""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from config import OUTPUT_DIR, ROOT
from db import db, init_db

LOG_DIR = OUTPUT_DIR / "logs"
LOG_FILE = LOG_DIR / "shtetlframes.log"

# Shared agent-debug sink (replaces the per-module _dbg/_agent_log/_train_dbg twins).
DEBUG_LOG = ROOT / "debug-30525a.log"
_DEBUG_SESSION = "30525a"
_DEBUG_INGEST_URL = "http://127.0.0.1:7406/ingest/637a1fe8-1535-4387-b632-3fb6093e59a2"
_debug_lock = threading.Lock()


def agent_dbg(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    *,
    run_id: str | None = None,
    tid: bool = False,
    post: bool = False,
) -> None:
    """Append one structured agent-debug payload to DEBUG_LOG (best-effort, never raises)."""
    try:
        payload: dict[str, Any] = {
            "sessionId": _DEBUG_SESSION,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        if run_id:
            payload["runId"] = run_id
        if tid:
            payload["tid"] = threading.get_ident()
        line = json.dumps(payload, default=str, ensure_ascii=False)
        with _debug_lock:
            with DEBUG_LOG.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        if post:
            try:
                import urllib.request

                req = urllib.request.Request(
                    _DEBUG_INGEST_URL,
                    data=line.encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Debug-Session-Id": _DEBUG_SESSION,
                    },
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=1.5)
            except Exception:
                pass
    except Exception:
        pass


def _ensure() -> None:
    init_db()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS error_log (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 ts REAL NOT NULL,
                 level TEXT DEFAULT 'error',
                 job TEXT DEFAULT '',
                 queue_id INTEGER,
                 url TEXT DEFAULT '',
                 message TEXT NOT NULL,
                 detail TEXT DEFAULT ''
               )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_ts ON error_log(ts DESC)")


def _console(line: str) -> None:
    try:
        print(line, flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass


def status(
    message: str,
    *,
    level: str = "info",
    job: str = "",
    queue_id: int | None = None,
    url: str = "",
    detail: str = "",
    persist: bool = False,
    console: bool = True,
) -> None:
    """Progress line — simple dashboard when enabled; else classic console print."""
    msg = (message or "").strip()
    if not msg:
        return
    dash_took = False
    if console:
        try:
            from console_dash import is_enabled, note_from_status

            if is_enabled():
                dash_took = note_from_status(msg, job=job)
        except Exception:
            dash_took = False
    if console and not dash_took:
        stamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"[ShtetlFrames {stamp}]"
        if job:
            prefix += f" {job}"
        _console(f"{prefix}: {msg}")
    if persist:
        log_event(
            msg,
            level=level,
            job=job,
            queue_id=queue_id,
            url=url,
            detail=detail,
            console=False,
        )


def _format_exc(exc: BaseException) -> str:
    """Best-effort traceback text — never raise (broken/rehydrated exceptions exist)."""
    try:
        return "".join(traceback.format_exception(exc))[-4000:]
    except Exception:
        pass
    try:
        tb = getattr(exc, "__traceback__", None)
        return "".join(traceback.format_exception(type(exc), exc, tb))[-4000:]
    except Exception:
        return f"{type(exc).__name__}: {exc}"[-4000:]


def log_event(
    message: str,
    *,
    level: str = "error",
    job: str = "",
    queue_id: int | None = None,
    url: str = "",
    detail: str = "",
    exc: BaseException | None = None,
    console: bool = True,
    fatal_dashboard: bool = False,
) -> None:
    """Write to SQLite error_log + text file (+ console by default).

    fatal_dashboard=True flips the CMD UI to the red error screen (job-level failures only).
    Per-video errors must leave the live scrape dashboard running.
    """
    _ensure()
    if exc is not None and not detail:
        detail = _format_exc(exc)
        # #region agent log
        agent_dbg(
            "H6",
            "logutil.py:log_event",
            "formatted_exc",
            {
                "exc_type": type(exc).__name__,
                "has_traceback_attr": hasattr(exc, "__traceback__"),
                "detail_len": len(detail or ""),
                "queue_id": queue_id,
                "fatal_dashboard": fatal_dashboard,
            },
            run_id="traceback-fix",
        )
        # #endregion
    ts = datetime.now(timezone.utc).timestamp()
    msg = (message or "")[:2000]
    det = (detail or "")[:8000]
    with db(write=True) as conn:
        conn.execute(
            """INSERT INTO error_log (ts, level, job, queue_id, url, message, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, level, job or "", queue_id, url or "", msg, det),
        )
    line = (
        f"{datetime.now(timezone.utc).isoformat()} [{level}] job={job} "
        f"qid={queue_id} url={(url or '')[:80]} | {msg}"
    )
    if det:
        line += f"\n  detail: {det[:500].replace(chr(10), ' / ')}"
    if console:
        try:
            from console_dash import is_enabled, set_error

            # Only job-level fatals should wipe the live worker dashboard.
            if is_enabled() and level == "error" and fatal_dashboard:
                set_error(msg)
            elif not is_enabled():
                _console(f"[ShtetlFrames] [{level}] {job or '-'} | {msg}")
                if det and level == "error":
                    _console(f"  detail: {det[:400].replace(chr(10), ' / ')}")
        except Exception:
            _console(f"[ShtetlFrames] [{level}] {job or '-'} | {msg}")
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            if LOG_FILE.stat().st_size > 5_000_000:
                bak = LOG_DIR / "shtetlframes.prev.log"
                if bak.exists():
                    bak.unlink()
                LOG_FILE.replace(bak)
    except OSError:
        pass


def recent_errors(limit: int = 50) -> list[dict]:
    _ensure()
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM error_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
