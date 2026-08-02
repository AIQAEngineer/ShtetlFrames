"""GET /api/candidates, GET /api/review/label_stats, POST /api/review."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import ParseResult, parse_qs

from api_http import json_response
from db import init_db, list_candidates, update_review


def load_candidates(limit: int = 5000) -> list[dict]:
    init_db()
    limit = max(1, min(int(limit or 5000), 20000))
    return list_candidates(limit=limit)


def handle_get_label_stats(handler: BaseHTTPRequestHandler) -> None:
    init_db()
    try:
        from label_feedback import compute_label_stats

        json_response(handler, 200, {"ok": True, **compute_label_stats()})
    except Exception as e:
        json_response(handler, 500, {"ok": False, "error": str(e)[:240]})


def handle_get_candidates(handler: BaseHTTPRequestHandler, parsed: ParseResult) -> None:
    qs = parse_qs(parsed.query)
    limit = int((qs.get("limit") or ["2000"])[0])
    limit = max(1, min(limit, 20000))
    # Gallery / "all" needs the full pool; otherwise keep the lighter default load.
    load_n = max(limit, 5000)
    rows = load_candidates(limit=load_n)
    status = (qs.get("status") or [""])[0].lower().strip()
    openai = (qs.get("openai") or [""])[0].lower().strip()
    show_all = status in ("all", "any") or openai in ("all", "any")
    show_openai_drop = openai == "drop" or status == "openai_drop"
    show_openai_keep = openai == "keep" or status == "openai_keep"
    show_openai_uncertain = openai == "uncertain" or status == "openai_uncertain"
    show_openai_none = openai in ("none", "skip", "unverified") or status in (
        "openai_none",
        "openai_skip",
        "unverified",
    )
    show_pending = status == "pending"
    show_human_accept = status == "accept"
    show_human_reject = status == "reject"
    # Default: when OpenAI verify is on, Review shows OpenAI keeps only.
    # status=all / openai=all: no AI gate (gallery wants pass + fail + not sent).
    # "To check" / Kept / Passed: human workflow — do not hide by OpenAI tag
    # (a human Keep must appear under Kept even if notes say openai:drop).
    # openai=keep / openai=drop / openai=none: explicit AI filters.
    try:
        from openai_verify import (
            notes_already_verified,
            notes_openai_approved,
            notes_openai_dropped,
            notes_openai_uncertain,
            openai_verify_enabled,
        )

        if show_openai_drop:
            rows = [r for r in rows if notes_openai_dropped(r.get("notes"))]
        elif show_openai_keep:
            rows = [r for r in rows if notes_openai_approved(r.get("notes"))]
        elif show_openai_uncertain:
            rows = [r for r in rows if notes_openai_uncertain(r.get("notes"))]
        elif show_openai_none:
            rows = [r for r in rows if not notes_already_verified(r.get("notes"))]
        elif show_all or show_pending or show_human_accept or show_human_reject:
            pass
        elif openai_verify_enabled():
            rows = [r for r in rows if notes_openai_approved(r.get("notes"))]
    except Exception:
        pass
    q = (qs.get("q") or [""])[0].lower().strip()
    if show_pending:
        rows = [r for r in rows if not (r.get("decision") or "").strip()]
    elif not show_openai_drop and not show_openai_keep and not show_openai_uncertain and not show_openai_none:
        if show_human_accept:
            rows = [r for r in rows if r.get("decision") == "accept"]
        elif show_human_reject:
            rows = [r for r in rows if r.get("decision") == "reject"]
    if q:
        rows = [
            r
            for r in rows
            if q in (r.get("video_id") or "").lower()
            or q in (r.get("best_cue") or "").lower()
        ]
    json_response(handler, 200, {"candidates": rows[:limit], "total": len(rows)})


def handle_get_stills_status(handler: BaseHTTPRequestHandler) -> None:
    """GET /api/stills/status — missing still count + backfill running flag."""
    init_db()
    try:
        from still_ensure import stills_status

        json_response(handler, 200, stills_status())
    except Exception as e:
        json_response(handler, 500, {"ok": False, "error": str(e)[:240]})


def handle_post_stills_backfill(handler: BaseHTTPRequestHandler, body: dict) -> None:
    """POST /api/stills/backfill — repair missing Review contact sheets."""
    init_db()
    try:
        from still_ensure import (
            backfill_missing_stills,
            kick_backfill_missing_stills,
            missing_still_ids,
        )

        sync = bool(body.get("sync"))
        limit = int(body.get("limit") or 5000)
        limit = max(1, min(limit, 20000))
        missing = missing_still_ids(limit=limit)
        if not missing:
            json_response(
                handler,
                200,
                {"ok": True, "missing": 0, "saved": 0, "failed": 0, "started": False},
            )
            return
        if sync:
            result = backfill_missing_stills(limit=limit)
            json_response(handler, 200, {**result, "started": False})
            return
        started = kick_backfill_missing_stills(limit=limit)
        json_response(
            handler,
            200,
            {
                "ok": True,
                "missing": len(missing),
                "started": started,
                "running": True,
                "message": "backfill running in background"
                if started
                else "backfill already running",
            },
        )
    except Exception as e:
        json_response(handler, 500, {"ok": False, "error": str(e)[:240]})


def handle_post_review(handler: BaseHTTPRequestHandler, body: dict) -> None:
    key = body.get("key")
    decision = body.get("decision", "")
    notes = body.get("notes", "")
    if not key:
        json_response(handler, 400, {"error": "key required"})
        return
    if decision not in ("", "accept", "reject", "clear"):
        json_response(handler, 400, {"error": "invalid decision"})
        return
    try:
        cand_id = int(key)
    except (TypeError, ValueError):
        json_response(handler, 400, {"error": "key must be candidate id"})
        return
    init_db()
    decision_final = "" if decision in ("", "clear") else decision
    update_review(cand_id, decision_final, notes or "")
    # Invalidate few-shot cache so next verify picks up new Keep/Pass stills.
    try:
        from label_feedback import build_fewshot_content_parts

        build_fewshot_content_parts(force=True)
    except Exception:
        pass
    if decision_final == "accept":
        try:
            from frame_strip import enqueue_strip_for_keep

            enqueue_strip_for_keep(cand_id)
        except Exception:
            pass
    json_response(
        handler,
        200,
        {"ok": True, "key": key, "decision": decision_final},
    )
