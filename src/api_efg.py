"""EFG downloads page APIs — import, park, rewrite, EFG-scoped scrape + monitor."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import ParseResult, parse_qs, urlparse

from api_http import json_response
from config import QUEUE_PAGE_SIZE
from db import clear_queue, init_db, list_queue_page, queue_stats

_rewrite_lock = threading.Lock()
_rewrite_running = False


def _host_of(url: str) -> str:
    try:
        return (urlparse(url or "").netloc or "").lower() or "?"
    except Exception:
        return "?"


def efg_host_breakdown(limit: int = 40) -> list[dict]:
    """Pending/done/error counts for EFG rows, grouped by URL host."""
    from db import db

    init_db()
    rows: dict[str, dict] = {}
    with db() as c:
        for r in c.execute(
            """
            SELECT url, status, COALESCE(downloadable,'yes') AS dl
            FROM queue_items
            WHERE source LIKE 'efg:%'
            """
        ):
            host = _host_of(r["url"])
            bucket = rows.setdefault(
                host, {"host": host, "pending": 0, "active": 0, "done": 0, "error": 0, "total": 0}
            )
            st = (r["status"] or "").lower()
            bucket["total"] += 1
            if st == "done":
                bucket["done"] += 1
            elif st == "error":
                bucket["error"] += 1
            elif st in ("scanning", "downloading", "uploading", "queued", "active"):
                bucket["active"] += 1
            elif r["dl"] == "yes":
                bucket["pending"] += 1
    out = sorted(rows.values(), key=lambda x: (-x["pending"], -x["total"], x["host"]))
    return out[: max(1, int(limit))]


def efg_kind_breakdown() -> list[dict]:
    from db import db

    init_db()
    out: list[dict] = []
    with db() as c:
        for r in c.execute(
            """
            SELECT source AS kind, COUNT(*) AS n,
                   SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done,
                   SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS error,
                   SUM(CASE WHEN status IN ('pending','queued')
                            AND COALESCE(downloadable,'yes')='yes' THEN 1 ELSE 0 END) AS pending
            FROM queue_items
            WHERE source LIKE 'efg:%'
            GROUP BY source
            ORDER BY n DESC
            """
        ):
            out.append({
                "kind": r["kind"] or "efg",
                "total": int(r["n"] or 0),
                "done": int(r["done"] or 0),
                "error": int(r["error"] or 0),
                "pending": int(r["pending"] or 0),
            })
    return out


def park_dead_efg_hosts() -> dict:
    """Park known-dead CDN hosts in the EFG queue (same markers as import skip)."""
    from db import db

    init_db()
    patterns = (
        ("%videocinecitta.bytewise.it%", "videocinecitta.bytewise.it 404"),
        ("%bytewise.it%", "bytewise.it dead CDN"),
        ("%repozytorium.fn.org.pl%", "fn.org.pl down"),
        ("%fn.org.pl%", "fn.org.pl down"),
        # Digilab download URLs return a login HTML page (200 text/html), not MP4.
        ("%portal.digilab.nfa.cz%", "digilab.nfa.cz login wall"),
    )
    parked = 0
    with db(write=True) as c:
        for like, reason in patterns:
            cur = c.execute(
                "UPDATE queue_items SET status='error', attempts=99, downloadable='no', "
                "error=? WHERE source LIKE 'efg:%' AND url LIKE ? AND status != 'done' AND "
                "(error IS NULL OR error NOT LIKE 'parked:%' OR attempts < 99)",
                (f"parked: {reason}", like),
            )
            parked += int(cur.rowcount or 0)
    return {"ok": True, "parked": parked, **queue_stats("efg")}


def handle_get_summary(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    from config import effective_scan_backend
    from db import get_job
    from pipeline_scrape import scrape_live_snapshot

    qs = parse_qs(parsed.query)
    try:
        host_limit = int((qs.get("hosts") or ["30"])[0] or 30)
    except (TypeError, ValueError):
        host_limit = 30
    json_response(handler, 200, {
        "queue": queue_stats("efg"),
        "kinds": efg_kind_breakdown(),
        "hosts": efg_host_breakdown(host_limit),
        "scrape": get_job("scrape"),
        "import": get_job("import"),
        "live": scrape_live_snapshot(),
        "backend": effective_scan_backend(),
    })


def handle_get_queue(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    qs = parse_qs(parsed.query)
    offset = int((qs.get("offset") or ["0"])[0] or 0)
    limit = int((qs.get("limit") or [str(QUEUE_PAGE_SIZE)])[0] or QUEUE_PAGE_SIZE)
    status = (qs.get("status") or [""])[0].strip()
    q = (qs.get("q") or [""])[0].strip()
    page = list_queue_page(offset=offset, limit=limit, status=status, q=q, source="efg")
    json_response(handler, 200, {**queue_stats("efg"), **page})


def handle_post_import(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """Import EFG discovery CSV only (no Europeana)."""
    from api_import import handle_post_import as _import

    body = dict(body or {})
    body["efg"] = True
    body["europeana"] = False
    _import(handler, body)


def handle_post_rewrite(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """Offline dead-CDN → YouTube rewrite, then optional re-import."""
    global _rewrite_running
    from db import set_job

    body = body if isinstance(body, dict) else {}
    do_import = body.get("import", True) is not False
    init_db()
    with _rewrite_lock:
        if _rewrite_running:
            json_response(handler, 409, {"ok": False, "error": "busy"})
            return
        _rewrite_running = True

    set_job("import", status="running", phase="rewrite", message="Rewriting EFG resolve…",
            progress=5, error="")

    def _run() -> None:
        global _rewrite_running
        try:
            from efg_rewrite import run_rewrite

            stats = run_rewrite()
            set_job("import", message=f"Rewrite done · {stats}", progress=40)
            result = {"rewrite": stats}
            if do_import:
                from discovery_import import import_into_queue

                def on_prog(msg: str) -> None:
                    try:
                        set_job("import", message=msg[:400], progress=70)
                    except Exception:
                        pass

                result["import"] = import_into_queue(
                    include_efg=True,
                    include_europeana=False,
                    on_progress=on_prog,
                )
            set_job(
                "import",
                status="done",
                phase="done",
                progress=100,
                message=f"Rewrite+import complete · {result.get('import', {}).get('n_added', 0)} added",
                completed=int((result.get("import") or {}).get("n_added") or 0),
            )
        except Exception as e:
            try:
                set_job("import", status="error", phase="error", progress=100, error=str(e)[:600])
            except Exception:
                pass
        finally:
            with _rewrite_lock:
                _rewrite_running = False

    threading.Thread(target=_run, daemon=True).start()
    json_response(handler, 200, {"ok": True, "job": "import"})


def handle_post_park(handler: BaseHTTPRequestHandler, body: dict) -> None:
    json_response(handler, 200, park_dead_efg_hosts())


def handle_post_scrape(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_scrape import start_scrape

    body = body if isinstance(body, dict) else {}
    result = start_scrape(
        max_videos=body.get("max_videos", "all"),
        workers=body.get("workers", 2),
        source="efg",
    )
    code = 200 if result.get("ok") else 409
    json_response(handler, code, result)


def handle_post_scrape_stop(handler: BaseHTTPRequestHandler, body: dict) -> None:
    from pipeline_scrape import stop_scrape
    from runpod_provision import set_pod_creates_blocked

    body = body if isinstance(body, dict) else {}
    block = body.get("block_pod_creates", True)
    if isinstance(block, str):
        block = block.strip().lower() not in ("0", "false", "no")
    if block:
        try:
            set_pod_creates_blocked(True)
        except Exception:
            pass
    result = stop_scrape(message=str(body.get("message") or "EFG scrape stopped"))
    json_response(handler, 200, {**result, "pod_creates_blocked": bool(block)})


def handle_post_queue_clear(handler: BaseHTTPRequestHandler, body: dict) -> None:
    init_db()
    n = clear_queue(source="efg")
    json_response(handler, 200, {"ok": True, "deleted": n, **queue_stats("efg")})
