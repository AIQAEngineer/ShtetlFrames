"""Clear Keep/Pass labels and rescore Chofetz + Munkacs local videos into Review."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from config import YOLO_WEIGHTS, load_env  # noqa: E402
from db import clear_candidates, db, init_db  # noqa: E402
from settings_store import apply_settings_to_environ  # noqa: E402
from shtetl_core.cues import (  # noqa: E402
    DEFAULT_SCORE_THRESHOLD,
    MIN_PERSON_AREA,
    MIN_PERSON_ASPECT,
    MIN_PERSON_HEIGHT,
    YOLO_CONF,
)
from shtetl_core.scoring import CueScorer, FrameHit  # noqa: E402
from shtetl_core.segments import aggregate_segments_dicts, write_sheet_from_crops  # noqa: E402

# Prefer local files; fall back to download only if missing.
JOBS = [
    {
        "video_id": "orthodox_look_training_reference",
        "title": "Rare Footage Of The Chofetz Chaim (YouTube train ref)",
        "url": "https://www.youtube.com/watch?v=87XlDRjmPME",
        "alt_urls": [
            "https://www.youtube.com/watch?v=VOD5ztsIqao",
            "https://upload.wikimedia.org/wikipedia/commons/f/ff/Historic_Chofetz_Chaim_Video_Almost_Unnoticed_For_Over_A_Decade_2.webm",
        ],
        "local_names": [
            "orthodox_look_training_reference.mp4",
            "orthodox_look_training_reference.webm",
            "agudah_1923_commons.webm",
            "agudah_1923_yt.mp4",
        ],
    },
    {
        "video_id": "munkacs_1933_yt",
        "title": "Jewish Life in Munkatch - March 1933 (complete)",
        "url": "https://www.youtube.com/watch?v=tdkNbcpCTc0",
        "alt_urls": ["https://www.youtube.com/watch?v=rp1OeIf0D0w"],
        "local_names": ["munkacs_1933_yt.mp4"],
    },
]


def _best_local_for_id(video_id: str) -> Path | None:
    """Prefer the largest playable video for an id (skip tiny audio-only side streams)."""
    videos = ROOT / "data" / "videos"
    if not videos.is_dir():
        return None
    cands: list[Path] = []
    for p in videos.iterdir():
        if p.suffix.lower() not in {".mp4", ".webm", ".mkv", ".mov"}:
            continue
        stem = p.stem.lower()
        # yt-dlp often leaves id.f396.mp4 + id.f251.webm before merge
        if stem == video_id.lower() or stem.startswith(video_id.lower() + "."):
            cands.append(p)
        elif stem.startswith(video_id.lower() + ".f"):
            cands.append(p)
    if not cands:
        return None
    # Drop tiny audio-ish files (<500KB) when a larger sibling exists.
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    best = cands[0]
    if best.stat().st_size < 500_000 and len(cands) == 1:
        return None
    return best


def _find_local(job: dict) -> Path | None:
    videos = ROOT / "data" / "videos"
    for name in job["local_names"]:
        p = videos / name
        if p.is_file() and p.stat().st_size > 500_000:
            return p
    by_id = _best_local_for_id(job["video_id"])
    if by_id:
        return by_id
    vid = job["video_id"]
    if "munk" in vid:
        keys = ["munk"]
    else:
        keys = ["chofetz", "agudah", "orthodox_look", "87xl", "vod5"]
    ranked: list[Path] = []
    for p in videos.iterdir():
        if p.suffix.lower() not in {".mp4", ".webm", ".mkv"}:
            continue
        low = p.name.lower()
        if any(k in low for k in keys) and p.stat().st_size > 500_000:
            ranked.append(p)
    if not ranked:
        return None
    ranked.sort(key=lambda p: p.stat().st_size, reverse=True)
    return ranked[0]


def _ensure_video(job: dict) -> Path:
    local = _find_local(job)
    if local:
        print(f"[{job['video_id']}] local {local.name} ({local.stat().st_size // 1024} KB)", flush=True)
        return local
    from download import download_entry

    urls = [job["url"], *job.get("alt_urls", [])]
    last = None
    for url in urls:
        print(f"[{job['video_id']}] downloading {url}", flush=True)
        info = download_entry(url, job["title"], video_id=job["video_id"])
        last = info
        # Prefer largest on-disk file for this id (meta path may point at audio-only).
        best = _best_local_for_id(job["video_id"])
        if best:
            return best
        path = info.get("path")
        if path and Path(path).is_file() and Path(path).stat().st_size > 500_000:
            return Path(path)
        print(f"  failed: {info.get('error')}", flush=True)
    raise FileNotFoundError(f"no local/download for {job['video_id']}: {last}")


def clear_labels(*, wipe: bool = True) -> dict:
    init_db()
    with db() as c:
        before = c.execute(
            "SELECT decision, COUNT(*) FROM candidates GROUP BY decision"
        ).fetchall()
        before = [tuple(r) for r in before]
        n = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    if wipe and n:
        # Fresh rescore: remove all Review candidates so we don't pile duplicates.
        clear_candidates()
    try:
        from db import clear_train_clips

        n_train = clear_train_clips()
    except Exception:
        n_train = 0
    with db() as c:
        after = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    print(
        f"cleared candidates (was {before}); train_clips_deleted={n_train}; left={after}",
        flush=True,
    )
    return {"before": before, "train_deleted": n_train, "left": after}


def scan_video(job: dict, video: Path, yolo: YOLO, scorer: CueScorer) -> list[dict]:
    from openai_verify import (
        format_verdict_notes,
        notes_openai_approved,
        openai_verify_enabled,
        verify_stills_any,
    )

    thr = float(DEFAULT_SCORE_THRESHOLD)
    video_id = job["video_id"]
    source_url = job["url"]
    print(f"[{video_id}] scan thr={thr} openai={openai_verify_enabled()}", flush=True)

    cap = cv2.VideoCapture(str(video))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    sample_fps = 0.5
    interval = max(1, int(round(fps / sample_fps)))
    hits: list[FrameHit] = []
    frame_idx = 0
    t0 = time.time()
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if frame_idx % interval != 0:
            frame_idx += 1
            continue
        t = frame_idx / fps
        results = yolo.predict(frame, conf=YOLO_CONF, classes=[0], verbose=False)
        frame_idx += 1
        if not results or results[0].boxes is None:
            continue
        frame_best = None
        for box in results[0].boxes:
            xyxy = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = map(int, xyxy)
            w, h = x2 - x1, y2 - y1
            if w <= 0 or h <= 0 or w * h < MIN_PERSON_AREA:
                continue
            if h < MIN_PERSON_HEIGHT or (h / float(w)) < MIN_PERSON_ASPECT:
                continue
            y2b = y1 + max(int(h * 0.60), min(h, int(h * 0.80)))
            crop = frame[
                max(0, y1) : min(frame.shape[0], y2b),
                max(0, x1) : min(frame.shape[1], x2),
            ]
            if crop.size == 0:
                continue
            ch, cw = crop.shape[:2]
            if ch < MIN_PERSON_HEIGHT or (ch / float(max(cw, 1))) < 0.95:
                continue
            pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            score, pos_s, neg_s, cue = scorer.score_image(pil)
            if score < thr:
                continue
            hit = FrameHit(
                video_id=video_id,
                time_sec=t,
                frame_idx=frame_idx,
                score=score,
                pos_score=pos_s,
                neg_score=neg_s,
                best_cue=cue,
                bbox=[float(x1), float(y1), float(x2), float(y2)],
                crop_path=None,
            )
            hit._pil = pil  # type: ignore[attr-defined]
            if frame_best is None or hit.score > frame_best.score:
                frame_best = hit
        if frame_best is not None:
            hits.append(frame_best)
            print(
                f"  HIT t={frame_best.time_sec:.1f}s score={frame_best.score:.3f} "
                f"cue={frame_best.best_cue[:50]}",
                flush=True,
            )
    cap.release()
    print(f"[{video_id}] frame_hits={len(hits)} elapsed={time.time()-t0:.1f}s", flush=True)
    if not hits:
        return []

    segs = aggregate_segments_dicts(hits, video_id)
    print(f"[{video_id}] segments={len(segs)}", flush=True)
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix=f"{video_id}_") as td:
        tmp = Path(td)
        for hi, h in enumerate(hits):
            pil = getattr(h, "_pil", None)
            if pil is None:
                continue
            cp = tmp / f"hit_{hi}_{h.time_sec:.1f}.jpg"
            pil.save(cp, quality=90)
            h.crop_path = str(cp)

        for i, seg in enumerate(segs, 1):
            group = seg.get("_hits") or []
            if not group:
                t0s = float(seg.get("start_sec") or 0)
                t1s = float(seg.get("end_sec") or t0s)
                group = [
                    h
                    for h in hits
                    if h.time_sec >= t0s - 0.5 and h.time_sec <= t1s + 0.5
                ]
            sheet_path = tmp / f"seg_{i}_sheet.jpg"
            wrote = write_sheet_from_crops(group, sheet_path) if group else None
            crop_paths = [
                h.crop_path
                for h in sorted(group, key=lambda x: -x.score)
                if getattr(h, "crop_path", None)
            ]
            row = {
                "video_id": video_id,
                "start_sec": seg.get("start_sec"),
                "end_sec": seg.get("end_sec"),
                "peak_score": seg.get("peak_score"),
                "mean_score": seg.get("mean_score"),
                "rank_score": seg.get("rank_score"),
                "hit_count": seg.get("hit_count"),
                "best_cue": seg.get("best_cue"),
                "source_url": source_url,
                "_local_still": str(wrote) if wrote else None,
            }
            if crop_paths and openai_verify_enabled():
                v = verify_stills_any(crop_paths, max_attempts=3)
                row["notes"] = format_verdict_notes(v)
                tag = "KEEP" if v.get("keep") else "DROP"
                print(
                    f"  seg#{i} [{tag}] {row['start_sec']}-{row['end_sec']}s "
                    f"peak={row['peak_score']:.3f} {(row['notes'] or '')[:160]}",
                    flush=True,
                )
            else:
                print(
                    f"  seg#{i} {row['start_sec']}-{row['end_sec']}s "
                    f"peak={row['peak_score']:.3f} (no openai)",
                    flush=True,
                )
            rows.append(row)

        # Insert while temp stills still exist (paths under TemporaryDirectory).
        keep_rows = [r for r in rows if notes_openai_approved(r.get("notes"))]
        if keep_rows:
            from db import insert_candidates

            n = insert_candidates(keep_rows)
            print(f"[{video_id}] inserted OpenAI keeps: {n}", flush=True)
        elif rows and not openai_verify_enabled():
            from db import insert_candidates

            n = insert_candidates(rows)
            print(f"[{video_id}] inserted CLIP segments (no openai): {n}", flush=True)
        else:
            print(f"[{video_id}] no keeps to insert (segs={len(rows)})", flush=True)
    return rows


def main() -> int:
    load_env()
    apply_settings_to_environ()
    load_env()

    # Already wiped on first run; keep wipe for fresh starts.
    clear_labels(wipe=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device}", flush=True)
    yolo = YOLO(YOLO_WEIGHTS)
    scorer = CueScorer(device=device)
    print(
        f"probe_path={getattr(scorer, 'probe_path', None)} "
        f"blend={getattr(scorer, 'probe_blend', None)}",
        flush=True,
    )

    summary = {}
    for job in JOBS:
        try:
            video = _ensure_video(job)
        except Exception as e:
            print(f"[{job['video_id']}] SKIP: {e}", flush=True)
            summary[job["video_id"]] = {"error": str(e)[:200]}
            continue
        rows = scan_video(job, video, yolo, scorer)
        summary[job["video_id"]] = {
            "segs": len(rows),
            "keeps": sum(
                1
                for r in rows
                if "openai:keep" in (r.get("notes") or "").lower()
            ),
        }

    init_db()
    with db() as c:
        by = c.execute(
            "SELECT video_id, decision, COUNT(*) FROM candidates GROUP BY 1,2"
        ).fetchall()
        total = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    print("DONE", json.dumps({"summary": summary, "db": by, "total": total}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
