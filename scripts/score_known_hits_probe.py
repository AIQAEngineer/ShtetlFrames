"""Score known-hit Keep stills + local known-positive videos with the new CLIP probe.

Writes:
  output/known_hit_probe/report.json
  output/known_hit_probe/index.html   (picked up vs missed grids)
  output/known_hit_probe/video_crops/ (person crops from video scan)
"""

from __future__ import annotations

import html
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from config import OUTPUT_DIR, VIDEOS_DIR, YOLO_WEIGHTS, load_env  # noqa: E402
from db import db, init_db  # noqa: E402
from media_files import VIDEO_EXTS  # noqa: E402
from shtetl_core.cues import (  # noqa: E402
    DEFAULT_SCORE_THRESHOLD,
    MIN_PERSON_AREA,
    MIN_PERSON_ASPECT,
    MIN_PERSON_HEIGHT,
    YOLO_CONF,
)
from shtetl_core.scoring import CueScorer  # noqa: E402
from still_store import candidate_still_path  # noqa: E402

OUT_DIR = OUTPUT_DIR / "known_hit_probe"
CROPS_DIR = OUT_DIR / "video_crops"
REPORT_JSON = OUT_DIR / "report.json"
REPORT_HTML = OUT_DIR / "index.html"

# Local known-positive titles to re-scan (short enough for a local pass).
KNOWN_VIDEOS = [
    {"video_id": "munkacs_1933_yt", "label": "Munkács 1933 (known positive)", "max_sec": None},
    # Kolbuszowa is ~28 min — sample first 8 minutes only.
    {"video_id": "kolbuszowa_yt", "label": "Kolbuszowa 1929 (known positive)", "max_sec": 480.0},
]


def _find_video(video_id: str) -> Path | None:
    matches = [
        p
        for p in VIDEOS_DIR.glob(f"{video_id}.*")
        if p.suffix.lower() in VIDEO_EXTS and p.stat().st_size > 500_000
    ]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_size)


def _load_keep_pil(cand_id: int, image_url: str | None):
    path = candidate_still_path(cand_id)
    if path.is_file() and path.stat().st_size > 200:
        return Image.open(path).convert("RGB"), path
    url = (image_url or "").strip()
    if url.startswith(("http://", "https://")):
        import requests
        from io import BytesIO

        r = requests.get(url, timeout=45)
        if r.status_code == 200 and len(r.content) > 200:
            return Image.open(BytesIO(r.content)).convert("RGB"), None
    return None, None


def score_keep_stills(scorer: CueScorer, thr: float) -> list[dict]:
    with db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, video_id, peak_score, best_cue, notes, image_url "
                "FROM candidates WHERE decision='accept' ORDER BY id ASC"
            ).fetchall()
        ]
    out: list[dict] = []
    for i, d in enumerate(rows, 1):
        cid = int(d["id"])
        img, still_path = _load_keep_pil(cid, d.get("image_url"))
        if img is None:
            out.append(
                {
                    "kind": "keep_still",
                    "id": cid,
                    "video_id": d.get("video_id"),
                    "status": "skip_no_still",
                    "picked_up": False,
                    "new_score": None,
                    "old_peak": d.get("peak_score"),
                    "cue": None,
                    "img": None,
                }
            )
            print(f"  [{i}/{len(rows)}] keep #{cid} SKIP no still", flush=True)
            continue
        score, pos, neg, cue = scorer.score_image(img)
        picked = float(score) >= thr
        rel = None
        if still_path is not None:
            # Prefer crop if present, else contact sheet via media route.
            rel = f"/media/sheet/cand_{cid}.jpg"
        row = {
            "kind": "keep_still",
            "id": cid,
            "video_id": d.get("video_id"),
            "status": "hit" if picked else "miss",
            "picked_up": picked,
            "new_score": round(float(score), 4),
            "pos": round(float(pos), 4),
            "neg": round(float(neg), 4),
            "old_peak": d.get("peak_score"),
            "old_cue": d.get("best_cue"),
            "cue": cue,
            "img": rel,
            "time_sec": None,
        }
        out.append(row)
        tag = "PICK" if picked else "MISS"
        print(
            f"  [{i}/{len(rows)}] keep #{cid} {tag} score={score:.3f} "
            f"vid={d.get('video_id')}",
            flush=True,
        )
    return out


def scan_known_video(
    *,
    video_id: str,
    label: str,
    path: Path,
    scorer: CueScorer,
    yolo: YOLO,
    thr: float,
    sample_fps: float = 1.0,
    max_sec: float | None = None,
) -> list[dict]:
    """Score every valid person crop; keep best per frame as hit or miss."""
    crop_dir = CROPS_DIR / video_id
    if crop_dir.exists():
        shutil.rmtree(crop_dir)
    crop_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"  cannot open {path}", flush=True)
        return []
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = (n_frames / fps) if n_frames and fps else 0.0
    limit = duration if max_sec is None else min(duration, float(max_sec))
    frame_interval = max(1, int(round(fps / max(sample_fps, 0.1))))
    print(
        f"  scanning {video_id}: {duration:.0f}s (limit {limit:.0f}s) "
        f"@ {sample_fps} fps",
        flush=True,
    )

    rows: list[dict] = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        time_sec = frame_idx / fps
        if time_sec > limit:
            break
        if frame_idx % frame_interval != 0:
            frame_idx += 1
            continue

        results = yolo.predict(frame, conf=YOLO_CONF, classes=[0], verbose=False)
        frame_idx += 1
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            continue

        best: dict | None = None
        best_pil = None
        for box in results[0].boxes:
            xyxy = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = map(int, xyxy)
            width, height = x2 - x1, y2 - y1
            if width <= 0 or height <= 0:
                continue
            if width * height < MIN_PERSON_AREA:
                continue
            if height < MIN_PERSON_HEIGHT:
                continue
            if (height / float(width)) < MIN_PERSON_ASPECT:
                continue
            y2b = y1 + max(int(height * 0.60), min(height, int(height * 0.80)))
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
            score, pos, neg, cue = scorer.score_image(pil)
            cand = {
                "score": float(score),
                "pos": float(pos),
                "neg": float(neg),
                "cue": cue,
                "bbox": [x1, y1, x2, y2],
                "time_sec": float(time_sec),
                "frame_idx": int(frame_idx),
            }
            if best is None or cand["score"] > best["score"]:
                best = cand
                best_pil = pil

        if best is None or best_pil is None:
            continue

        picked = best["score"] >= thr
        fname = f"{video_id}_t{best['time_sec']:07.1f}s_{'hit' if picked else 'miss'}.jpg"
        dest = crop_dir / fname
        best_pil.save(dest, quality=85)
        rows.append(
            {
                "kind": "video_frame",
                "id": None,
                "video_id": video_id,
                "label": label,
                "status": "hit" if picked else "miss",
                "picked_up": picked,
                "new_score": round(best["score"], 4),
                "pos": round(best["pos"], 4),
                "neg": round(best["neg"], 4),
                "old_peak": None,
                "cue": best["cue"],
                "img": f"/media/known_hit_probe/video_crops/{video_id}/{fname}",
                "time_sec": round(best["time_sec"], 1),
            }
        )
        if len(rows) % 10 == 0:
            print(
                f"    t={best['time_sec']:.0f}s frames_scored={len(rows)} "
                f"last={best['score']:+.3f}",
                flush=True,
            )

    cap.release()
    n_hit = sum(1 for r in rows if r["picked_up"])
    print(
        f"  {video_id}: {n_hit}/{len(rows)} person-frames above thr={thr}",
        flush=True,
    )
    return rows


def _card(item: dict) -> str:
    score = item.get("new_score")
    score_s = f"{score:+.3f}" if score is not None else "—"
    cue = html.escape(str(item.get("cue") or "")[:70])
    vid = html.escape(str(item.get("video_id") or ""))
    t = item.get("time_sec")
    t_s = f" @ {t:.1f}s" if t is not None else ""
    cid = item.get("id")
    id_s = f"#{cid}" if cid is not None else ""
    img = item.get("img") or ""
    img_tag = (
        f'<img src="{html.escape(img)}" loading="lazy" alt="{vid}{t_s}" />'
        if img
        else '<div class="noimg">no still</div>'
    )
    klass = "hit" if item.get("picked_up") else "miss"
    return f"""
    <article class="card {klass}">
      {img_tag}
      <div class="meta">
        <div class="score">{score_s}</div>
        <div class="vid">{id_s} {vid}{html.escape(t_s)}</div>
        <div class="cue">{cue}</div>
      </div>
    </article>"""


def write_html(report: dict) -> None:
    keeps = [r for r in report["items"] if r["kind"] == "keep_still"]
    frames = [r for r in report["items"] if r["kind"] == "video_frame"]
    keep_hit = [r for r in keeps if r.get("status") == "hit"]
    keep_miss = [r for r in keeps if r.get("status") == "miss"]
    keep_skip = [r for r in keeps if r.get("status") == "skip_no_still"]
    frame_hit = [r for r in frames if r.get("picked_up")]
    frame_miss = [r for r in frames if not r.get("picked_up")]
    # Show worst misses first (closest to threshold last among misses)
    keep_miss_sorted = sorted(keep_miss, key=lambda r: (r.get("new_score") is None, r.get("new_score") or 0))
    frame_miss_sorted = sorted(frame_miss, key=lambda r: r.get("new_score") or 0)
    frame_hit_sorted = sorted(frame_hit, key=lambda r: -(r.get("new_score") or 0))
    keep_hit_sorted = sorted(keep_hit, key=lambda r: -(r.get("new_score") or 0))

    s = report["summary"]
    probe = report.get("probe") or {}

    def section(title: str, items: list[dict], empty: str) -> str:
        if not items:
            return f"<section><h2>{html.escape(title)}</h2><p class='empty'>{html.escape(empty)}</p></section>"
        cards = "\n".join(_card(i) for i in items)
        return f"<section><h2>{html.escape(title)} <span class='n'>({len(items)})</span></h2><div class='grid'>{cards}</div></section>"

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Known hits × new CLIP probe</title>
<style>
  :root {{
    --bg: #0f1115; --panel: #171a21; --text: #e8eaed; --muted: #9aa0a6;
    --hit: #1e3a2f; --hitb: #3dd68c; --miss: #3a1e1e; --missb: #f07178;
    --line: #2a2f3a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.4;
  }}
  header {{
    padding: 1.5rem 1.75rem 1rem; border-bottom: 1px solid var(--line);
    background: var(--panel);
  }}
  h1 {{ margin: 0 0 .35rem; font-size: 1.45rem; font-weight: 650; }}
  h2 {{ margin: 0 0 .75rem; font-size: 1.05rem; font-weight: 600; }}
  h2 .n {{ color: var(--muted); font-weight: 500; }}
  .sub {{ color: var(--muted); font-size: .92rem; max-width: 70rem; }}
  .stats {{
    display: flex; flex-wrap: wrap; gap: .6rem; margin-top: 1rem;
  }}
  .stat {{
    background: #12151c; border: 1px solid var(--line); border-radius: 8px;
    padding: .55rem .8rem; min-width: 7.5rem;
  }}
  .stat b {{ display: block; font-size: 1.25rem; }}
  .stat span {{ color: var(--muted); font-size: .78rem; }}
  main {{ padding: 1.25rem 1.75rem 3rem; display: grid; gap: 1.75rem; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: .75rem;
  }}
  .card {{
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 10px; overflow: hidden; display: flex; flex-direction: column;
  }}
  .card.hit {{ border-color: #2a5a42; }}
  .card.miss {{ border-color: #5a2a2a; }}
  .card img, .card .noimg {{
    width: 100%; aspect-ratio: 3/4; object-fit: cover; background: #0a0c10;
    display: block;
  }}
  .card .noimg {{
    display: grid; place-items: center; color: var(--muted); font-size: .8rem;
  }}
  .meta {{ padding: .5rem .55rem .65rem; font-size: .78rem; }}
  .score {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
  .card.hit .score {{ color: var(--hitb); }}
  .card.miss .score {{ color: var(--missb); }}
  .vid {{ color: var(--muted); margin-top: .15rem; word-break: break-all; }}
  .cue {{ margin-top: .25rem; color: #c5c9d0; }}
  .empty {{ color: var(--muted); }}
  .legend {{ display: flex; gap: 1rem; margin-top: .75rem; font-size: .85rem; }}
  .pill {{
    display: inline-flex; align-items: center; gap: .35rem;
    padding: .15rem .55rem; border-radius: 999px; border: 1px solid var(--line);
  }}
  .pill.hit {{ background: var(--hit); border-color: #2a5a42; }}
  .pill.miss {{ background: var(--miss); border-color: #5a2a2a; }}
</style>
</head>
<body>
<header>
  <h1>Known hits × new CLIP probe</h1>
  <p class="sub">
    Human Keep stills and local known-positive videos rescored with
    OpenCLIP ViT-L-14 + linear probe
    (blend={html.escape(str(probe.get('blend')))},
    val_acc={html.escape(str(probe.get('val_acc')))},
    n_keep={html.escape(str(probe.get('n_keep')))}/n_pass={html.escape(str(probe.get('n_pass')))}).
    Gate threshold = {s.get('score_threshold')}.
  </p>
  <div class="legend">
    <span class="pill hit">picked up ≥ thr</span>
    <span class="pill miss">missed &lt; thr</span>
  </div>
  <div class="stats">
    <div class="stat"><b>{s.get('keep_hit', 0)}/{s.get('keep_scored', 0)}</b><span>Keeps picked up</span></div>
    <div class="stat"><b>{s.get('keep_miss', 0)}</b><span>Keeps missed</span></div>
    <div class="stat"><b>{s.get('video_hit', 0)}</b><span>Video frames picked up</span></div>
    <div class="stat"><b>{s.get('video_miss', 0)}</b><span>Video frames missed</span></div>
    <div class="stat"><b>{s.get('videos_scanned', 0)}</b><span>Videos scanned</span></div>
  </div>
</header>
<main>
  {section("Keep stills — picked up", keep_hit_sorted, "None cleared the gate.")}
  {section("Keep stills — missed", keep_miss_sorted, "All scored Keeps cleared the gate.")}
  {section("Video person-frames — picked up", frame_hit_sorted[:120], "No frames above threshold.")}
  {section("Video person-frames — missed (person detected, below gate)", frame_miss_sorted[:120], "No below-threshold person frames.")}
  {"" if not keep_skip else section("Keep stills — no image on disk", keep_skip, "")}
</main>
</body>
</html>
"""
    REPORT_HTML.write_text(body, encoding="utf-8")


def main() -> int:
    load_env()
    os.environ.setdefault("CLIP_PROBE", "1")
    init_db()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CROPS_DIR.mkdir(parents=True, exist_ok=True)

    thr = float(DEFAULT_SCORE_THRESHOLD)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} thr={thr} CLIP_PROBE={os.environ.get('CLIP_PROBE')}", flush=True)

    scorer = CueScorer(device=device)
    if scorer.probe is None:
        print("ERROR: probe.pt did not load — aborting", flush=True)
        return 1
    print(
        f"probe={scorer.probe_path} blend={scorer.probe_blend}",
        flush=True,
    )

    probe_meta: dict = {
        "path": str(scorer.probe_path),
        "blend": scorer.probe_blend,
    }
    try:
        payload = torch.load(scorer.probe_path, map_location="cpu", weights_only=False)
        for k in ("val_acc", "n_keep", "n_pass", "epochs_ran", "trained_at"):
            if k in payload:
                probe_meta[k] = payload[k]
    except Exception as e:
        probe_meta["meta_error"] = str(e)[:120]

    print("\n=== Keep stills (decision=accept) ===", flush=True)
    keep_rows = score_keep_stills(scorer, thr)

    print("\n=== Known-positive videos ===", flush=True)
    yolo = YOLO(YOLO_WEIGHTS)
    video_rows: list[dict] = []
    videos_scanned = 0
    for spec in KNOWN_VIDEOS:
        vid = spec["video_id"]
        path = _find_video(vid)
        if path is None:
            print(f"  missing video for {vid}", flush=True)
            continue
        videos_scanned += 1
        video_rows.extend(
            scan_known_video(
                video_id=vid,
                label=spec["label"],
                path=path,
                scorer=scorer,
                yolo=yolo,
                thr=thr,
                sample_fps=1.0,
                max_sec=spec.get("max_sec"),
            )
        )

    items = keep_rows + video_rows
    keep_scored = [r for r in keep_rows if r["status"] != "skip_no_still"]
    summary = {
        "ts": int(time.time()),
        "score_threshold": thr,
        "device": device,
        "keep_total": len(keep_rows),
        "keep_scored": len(keep_scored),
        "keep_hit": sum(1 for r in keep_scored if r["picked_up"]),
        "keep_miss": sum(1 for r in keep_scored if not r["picked_up"]),
        "keep_skip": sum(1 for r in keep_rows if r["status"] == "skip_no_still"),
        "video_hit": sum(1 for r in video_rows if r["picked_up"]),
        "video_miss": sum(1 for r in video_rows if not r["picked_up"]),
        "video_frames": len(video_rows),
        "videos_scanned": videos_scanned,
        "all_keeps_picked_up": (
            len(keep_scored) > 0
            and all(r["picked_up"] for r in keep_scored)
        ),
    }
    report = {"summary": summary, "probe": probe_meta, "items": items}
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_html(report)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"wrote {REPORT_JSON}", flush=True)
    print(f"wrote {REPORT_HTML}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
