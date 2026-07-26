"""Rescore Munkács local mp4 on the GPU pod with current male/body gates."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import ROOT as CFG_ROOT, load_env  # noqa: E402
import config as app_config  # noqa: E402
from settings_store import apply_settings_to_environ  # noqa: E402

VIDEO_ID = "munkacs_1933_yt"
SOURCE_URL = "https://www.youtube.com/watch?v=tdkNbcpCTc0"
TITLE = "Jewish Life in Munkatch - March 1933 (complete)"
LOCAL_VIDEO = ROOT / "data" / "videos" / f"{VIDEO_ID}.mp4"


def _push_scoring(base: str) -> None:
    batches = [
        [
            ("src/shtetl_core/cues.py", "shtetl_core/cues.py"),
            ("src/shtetl_core/scoring.py", "shtetl_core/scoring.py"),
        ],
        [
            ("src/shtetl_core/scan.py", "shtetl_core/scan.py"),
            ("src/shtetl_core/__init__.py", "shtetl_core/__init__.py"),
        ],
        [("runpod_worker/entry.py", "entry.py")],
        [("src/openai_verify.py", "openai_verify.py")],
    ]
    for batch in batches:
        files = {
            dest: (CFG_ROOT / rel).read_text(encoding="utf-8")
            for rel, dest in batch
            if (CFG_ROOT / rel).is_file()
        }
        if not files:
            continue
        r = requests.post(f"{base}/sync_push", json={"files": files}, timeout=180)
        print(
            f"sync_push {list(files)} -> {r.status_code} {(r.text or '')[:180]}",
            flush=True,
        )
        time.sleep(1.0)
    try:
        print("cues", requests.get(f"{base}/cues_config", timeout=30).json(), flush=True)
    except Exception as e:
        print("cues_config err", e, flush=True)


def main() -> int:
    load_env()
    apply_settings_to_environ()
    load_env()

    from db import init_db, insert_candidates
    from openai_verify import (
        filter_candidates_openai,
        notes_openai_approved,
        notes_openai_dropped,
        openai_verify_enabled,
    )
    from runpod_client import _hydrate_segment_stills, segments_to_candidate_rows
    from runpod_provision import find_shtetl_pods, pod_proxy_url

    if not LOCAL_VIDEO.is_file():
        print(f"missing {LOCAL_VIDEO}", flush=True)
        return 1

    pods = [p for p in find_shtetl_pods() if (p.get("desiredStatus") or "") == "RUNNING"]
    if not pods:
        print("no running pod", flush=True)
        return 1
    base = pod_proxy_url(pods[0]["id"]).rstrip("/")
    print(f"pod {pods[0].get('name')} {base}", flush=True)
    _push_scoring(base)

    thr = float(getattr(app_config, "SCORE_THRESHOLD", None) or 0.04)
    qid = f"probe-munkacs-{int(time.time())}"
    print(
        f"upload+scan {LOCAL_VIDEO.name} ({LOCAL_VIDEO.stat().st_size/1e6:.1f} MB) "
        f"thr={thr} openai={openai_verify_enabled()} qid={qid}",
        flush=True,
    )

    with LOCAL_VIDEO.open("rb") as fh:
        r = requests.post(
            f"{base}/scan_file",
            files={"video": (LOCAL_VIDEO.name, fh, "video/mp4")},
            data={
                "title": TITLE,
                "queue_id": qid,
                "source_url": SOURCE_URL,
                "sample_fps": "0.5",
                "score_threshold": str(thr),
            },
            timeout=1200,
        )
    print(f"scan_file status={r.status_code}", flush=True)
    try:
        out = r.json()
    except Exception:
        print((r.text or "")[:500], flush=True)
        return 1

    print(f"ok={out.get('ok')} error={out.get('error')}", flush=True)
    _hydrate_segment_stills(base, out)
    segs = out.get("segments") or []
    print(f"segments={len(segs)}", flush=True)
    for i, s in enumerate(segs, 1):
        print(
            f"  seg#{i} {s.get('start_sec')}-{s.get('end_sec')}s "
            f"peak={s.get('peak_score')} cue={s.get('best_cue')} "
            f"notes={(s.get('notes') or '')[:200]}",
            flush=True,
        )

    rows = segments_to_candidate_rows(out, source_url=SOURCE_URL)
    for row in rows:
        row["video_id"] = VIDEO_ID
    need_pc = [
        row
        for row in rows
        if "openai:" not in (row.get("notes") or "")
        and "vlm:" not in (row.get("notes") or "")
    ]
    if need_pc and openai_verify_enabled():
        print(f"PC verify for {len(need_pc)} untagged", flush=True)
        rows = filter_candidates_openai(
            rows, on_status=lambda m: print(f"  filter: {m}", flush=True)
        )

    keeps: list[int] = []
    drops: list[int] = []
    for i, row in enumerate(rows, 1):
        notes = row.get("notes") or ""
        if notes_openai_approved(notes):
            tag = "KEEP"
            keeps.append(i)
        elif notes_openai_dropped(notes):
            tag = "DROP"
            drops.append(i)
        else:
            tag = "OTHER"
        print(
            f"#{i} [{tag}] {row.get('start_sec')}-{row.get('end_sec')}s "
            f"peak={row.get('peak_score')} rank={row.get('rank_score')} "
            f"cue={row.get('best_cue')}",
            flush=True,
        )
        print(f"    {str(notes)[:280]}", flush=True)

    init_db()
    keep_rows = [row for row in rows if notes_openai_approved(row.get("notes") or "")]
    if keep_rows:
        n = insert_candidates(keep_rows)
        print(f"inserted keeps into Review DB: {n}", flush=True)
    else:
        print("no keeps to insert", flush=True)

    print("---", flush=True)
    print(f"CLIP segments: {len(segs)}", flush=True)
    print(f"OpenAI keeps: {keeps}", flush=True)
    print(f"OpenAI drops: {drops}", flush=True)
    print(f"WOULD_ENTER_REVIEW={bool(keeps)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
