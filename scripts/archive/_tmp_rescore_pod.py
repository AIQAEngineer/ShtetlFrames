"""Clear Review Keep/Pass and rescore local Chofetz + Munkacs via GPU /scan_file."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env  # noqa: E402
from db import clear_candidates, db, init_db, insert_candidates  # noqa: E402
from runpod_client import segments_to_candidate_rows  # noqa: E402
from runpod_provision import find_shtetl_pods, pod_proxy_url  # noqa: E402
from settings_store import apply_settings_to_environ  # noqa: E402
from shtetl_core.cues import DEFAULT_SCORE_THRESHOLD  # noqa: E402

JOBS = [
    {
        "video_id": "orthodox_look_training_reference",
        "title": "Rare Footage Of The Chofetz Chaim",
        "url": "https://www.youtube.com/watch?v=87XlDRjmPME",
        "path": ROOT
        / "data"
        / "videos"
        / "orthodox_look_training_reference.f396.mp4",
    },
    {
        "video_id": "munkacs_1933_yt",
        "title": "Jewish Life in Munkatch - March 1933",
        "url": "https://www.youtube.com/watch?v=tdkNbcpCTc0",
        "path": ROOT / "data" / "videos" / "munkacs_1933_yt.mp4",
    },
]


def main() -> int:
    load_env()
    apply_settings_to_environ()
    init_db()
    clear_candidates()
    try:
        from db import clear_train_clips

        clear_train_clips()
    except Exception:
        pass
    print("cleared Review candidates + train clips", flush=True)

    pods = find_shtetl_pods()
    if not pods:
        print("no GPU pod", flush=True)
        return 1
    base = pod_proxy_url(pods[0]["id"]).rstrip("/")
    thr = float(DEFAULT_SCORE_THRESHOLD)
    print(f"pod={base} thr={thr}", flush=True)

    # Confirm probe present
    try:
        r = requests.post(base + "/clip_probe", json={}, timeout=20)
        print("clip_probe ping", r.status_code, r.text[:120], flush=True)
    except Exception as e:
        print("clip_probe ping err", e, flush=True)

    summary = {}
    for job in JOBS:
        path: Path = job["path"]
        if not path.is_file():
            print(f"MISSING {path}", flush=True)
            summary[job["video_id"]] = {"error": "missing"}
            continue
        print(f"upload+scan {job['video_id']} ({path.stat().st_size // 1024} KB)…", flush=True)
        t0 = time.time()
        with path.open("rb") as f:
            r = requests.post(
                f"{base}/scan_file",
                files={"video": (path.name, f, "video/mp4")},
                data={
                    "title": job["video_id"],
                    "source_url": job["url"],
                    "sample_fps": "0.5",
                    "score_threshold": str(thr),
                },
                timeout=1800,
            )
        elapsed = time.time() - t0
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:400]}
        print(f"  http={r.status_code} elapsed={elapsed:.1f}s ok={body.get('ok')}", flush=True)
        if not body.get("ok"):
            print(f"  err={str(body)[:400]}", flush=True)
            summary[job["video_id"]] = {"error": str(body)[:200]}
            continue
        # Attach source_url for DB
        segs = body.get("segments") or body.get("hits") or []
        out = dict(body)
        out["source_url"] = job["url"]
        out["url"] = job["url"]
        rows = segments_to_candidate_rows(out, source_url=job["url"])
        for row in rows:
            row["video_id"] = job["video_id"]
            row["source_url"] = job["url"]
        # Prefer OpenAI-approved if notes present; else all CLIP segments
        keeps = [
            row
            for row in rows
            if "openai:keep" in (row.get("notes") or "").lower()
            or "openai:drop" not in (row.get("notes") or "").lower()
        ]
        # If any openai tags exist, only insert keeps
        if any("openai:" in (row.get("notes") or "").lower() for row in rows):
            keeps = [
                row
                for row in rows
                if "openai:keep" in (row.get("notes") or "").lower()
            ]
        n = insert_candidates(keeps) if keeps else 0
        print(
            f"  segments={len(rows)} inserted={n} "
            f"n_hits={body.get('n_hits')} peaksample={[(x.get('start_sec'), x.get('peak_score')) for x in rows[:5]]}",
            flush=True,
        )
        summary[job["video_id"]] = {
            "segs": len(rows),
            "inserted": n,
            "elapsed": round(elapsed, 1),
        }

    with db() as c:
        by = [tuple(r) for r in c.execute(
            "SELECT video_id, COUNT(*), "
            "SUM(CASE WHEN notes LIKE '%openai:keep%' THEN 1 ELSE 0 END) "
            "FROM candidates GROUP BY 1"
        )]
        total = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    print("DONE", json.dumps({"summary": summary, "db": by, "total": total}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
