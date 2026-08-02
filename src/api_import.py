"""Discovery import API — load EFG/Europeana discovery CSVs into the queue.

Runs as a background job (`import` job id) so a large Europeana resolve does
not block the HTTP request. GET /api/jobs/import polls progress.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler

from api_http import json_response

_lock = threading.Lock()
_running = False


def _job():
    from db import get_job

    return get_job("import")


def handle_post_import(handler: BaseHTTPRequestHandler, body: dict) -> None:
    global _running
    from db import init_db, set_job

    body = body if isinstance(body, dict) else {}
    include_efg = body.get("efg", True) is not False
    include_europeana = body.get("europeana", True) is not False
    resolve_europeana = body.get("resolve_europeana", True) is not False
    try:
        europeana_limit = int(body.get("europeana_limit") or 0)
    except (TypeError, ValueError):
        europeana_limit = 0

    init_db()
    with _lock:
        cur = _job()
        if _running or cur.get("status") == "running":
            json_response(handler, 409, {"ok": False, "error": "busy", "job": cur})
            return
        _running = True

    set_job("import", status="running", phase="importing", message="Importing…",
            progress=2, error="")

    def _run():
        global _running
        try:
            from discovery_import import import_into_queue

            def on_prog(msg: str) -> None:
                try:
                    set_job("import", message=msg[:400])
                except Exception:
                    pass

            result = import_into_queue(
                include_efg=include_efg,
                include_europeana=include_europeana,
                resolve_europeana=resolve_europeana,
                europeana_limit=europeana_limit,
                on_progress=on_prog,
            )
            set_job(
                "import",
                status="done",
                phase="done",
                progress=100,
                completed=result.get("n_added", 0),
                total=result.get("attempted", 0),
                message=(f"Added {result.get('n_added', 0)} · skipped {result.get('n_skipped', 0)} "
                         f"of {result.get('attempted', 0)}"),
            )
        except Exception as e:
            try:
                set_job("import", status="error", phase="error", progress=100, error=str(e)[:600])
            except Exception:
                pass
        finally:
            _running = False

    threading.Thread(target=_run, name="import-discoveries", daemon=True).start()
    json_response(handler, 200, {"ok": True, "job": _job()})
