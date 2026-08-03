"""Sequential video decode + YOLO person crops + CLIP scoring."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import cv2
from PIL import Image
from ultralytics import YOLO

import shtetl_core.cues as _cues
from shtetl_core.blur import effective_score_threshold, is_blurry_crop
from shtetl_core.scoring import CueScorer, FrameHit

# getattr so a half-synced pod (new scan.py + old cues.py) still warms.
DEFAULT_FPS = float(getattr(_cues, "DEFAULT_FPS", 1.5))
DEFAULT_SCORE_THRESHOLD = float(getattr(_cues, "DEFAULT_SCORE_THRESHOLD", 0.10))
MIN_PERSON_AREA = int(getattr(_cues, "MIN_PERSON_AREA", 40 * 80))
MIN_PERSON_ASPECT = float(getattr(_cues, "MIN_PERSON_ASPECT", 1.15))
MIN_PERSON_HEIGHT = int(getattr(_cues, "MIN_PERSON_HEIGHT", 100))
MIN_PERSON_WIDTH = int(getattr(_cues, "MIN_PERSON_WIDTH", 120))
MIN_SHARPNESS_LAPLACIAN = float(getattr(_cues, "MIN_SHARPNESS_LAPLACIAN", 150.0))
MIN_CROP_SHORT_SIDE = int(getattr(_cues, "MIN_CROP_SHORT_SIDE", 96))
YOLO_CONF = float(getattr(_cues, "YOLO_CONF", 0.32))

ProgressCallback = Callable[[float, float, int], None]


def sample_frame_indices(n_frames: int, fps: float, sample_fps: float) -> list[int]:
    if n_frames <= 0 or fps <= 0:
        return []
    step = max(1, int(round(fps / sample_fps)))
    return list(range(0, n_frames, step))


def scan_video(
    video_path: Path,
    video_id: str,
    scorer: CueScorer,
    yolo: YOLO,
    sample_fps: float = DEFAULT_FPS,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    save_crops_dir: Path | None = None,
    on_progress: ProgressCallback | None = None,
    lowres_relaxed: bool = False,
) -> list[FrameHit]:
    """
    Walk the video sequentially (seek is unreliable on archival WebM/AVI).
    Keep the best person crop per sampled frame above score_threshold.

    ``lowres_relaxed`` (e.g. 384×288 newsreels): person crops can never reach
    the 240px still-tuned gates, so skip the blur/sharpness gate and relax the
    person-box minimums — the CLIP score threshold does the quality gating.
    """
    if lowres_relaxed:
        min_h, min_w, min_area = 50, 50, 1500
    else:
        min_h = MIN_PERSON_HEIGHT
        min_w = MIN_PERSON_WIDTH
        min_area = MIN_PERSON_AREA
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = (n_frames / fps) if n_frames > 0 and fps > 0 else 0.0
    frame_interval = max(1, int(round(fps / max(sample_fps, 0.1))))
    hits: list[FrameHit] = []

    if save_crops_dir:
        save_crops_dir.mkdir(parents=True, exist_ok=True)

    frame_idx = 0
    last_prog = -1
    last_wall = time.time()
    if on_progress is not None:
        try:
            on_progress(0.0, duration, 0)
        except Exception:
            pass

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if frame_idx % frame_interval != 0:
            frame_idx += 1
            continue
        time_sec = frame_idx / fps
        now = time.time()
        if on_progress is not None:
            bucket = int(time_sec // 5)
            if bucket != last_prog or (now - last_wall) >= 3.0:
                last_prog = bucket
                last_wall = now
                try:
                    on_progress(time_sec, duration, len(hits))
                except Exception:
                    pass
        results = yolo.predict(frame, conf=YOLO_CONF, classes=[0], verbose=False)
        frame_idx += 1
        if not results:
            continue
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            continue

        frame_best: FrameHit | None = None
        for box in boxes:
            xyxy = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = map(int, xyxy)
            width, height = x2 - x1, y2 - y1
            if width <= 0 or height <= 0:
                continue
            if width * height < min_area:
                continue
            # Reject face-square / tiny head boxes — need a taller person shape.
            if height < min_h:
                continue
            if width < min_w:
                continue
            if (height / float(width)) < MIN_PERSON_ASPECT:
                continue
            # Prefer upper body for clothing / hat / payot cues (not face-only).
            # Keep at least ~60% of box height so shoulders/chest stay in frame.
            y2b = y1 + max(int(height * 0.60), min(height, int(height * 0.80)))
            crop = frame[
                max(0, y1) : min(frame.shape[0], y2b),
                max(0, x1) : min(frame.shape[1], x2),
            ]
            if crop.size == 0:
                continue
            # Crop itself must still look like upper body, not a postage-stamp face.
            ch, cw = crop.shape[:2]
            if ch < min_h or cw < min_w or (ch / float(max(cw, 1))) < 0.95:
                continue
            # Soft / motion-blurred / tiny-upscale crops — don't waste CLIP on them.
            # lowres_relaxed: skip entirely — on sub-SD archival frames every
            # crop fails the still-tuned px gates; CLIP score is the arbiter.
            if not lowres_relaxed and is_blurry_crop(
                crop,
                min_laplacian=MIN_SHARPNESS_LAPLACIAN,
                min_short_side=MIN_CROP_SHORT_SIDE,
            ):
                continue
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            score, pos_s, neg_s, cue = scorer.score_image(pil)
            # Sharp large crops may use HQ_SCORE_THRESHOLD (lower); soft stay at base.
            thr = effective_score_threshold(crop, score_threshold)
            if score < thr:
                continue
            crop_path = None
            if save_crops_dir is not None:
                crop_path = str(save_crops_dir / f"{video_id}_{frame_idx}_{x1}_{y1}.jpg")
                pil.save(crop_path, quality=85)
            hit = FrameHit(
                video_id=video_id,
                time_sec=time_sec,
                frame_idx=frame_idx,
                score=score,
                pos_score=pos_s,
                neg_score=neg_s,
                best_cue=cue,
                bbox=[float(x1), float(y1), float(x2), float(y2)],
                crop_path=crop_path,
            )
            if frame_best is None or hit.score > frame_best.score:
                frame_best = hit
        if frame_best is not None:
            hits.append(frame_best)

    cap.release()
    return hits


def score_person_crops(
    frame_bgr,
    *,
    video_id: str,
    scorer: CueScorer,
    yolo: YOLO,
    time_sec: float = 0.0,
    frame_idx: int = 0,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    save_crops_dir: Path | None = None,
    min_person_width: int | None = None,
    min_person_height: int | None = None,
    min_person_area: int | None = None,
    min_crop_short_side: int | None = None,
    min_laplacian: float | None = None,
    min_denoise_laplacian: float | None = None,
    still_relaxed: bool = False,
) -> list[FrameHit]:
    """YOLO person → upper-body crop → blur gate → CLIP (shared by video + stills).

    ``still_relaxed`` (archive plates): smaller people in group photos clear gates
    that were tightened for soft EFG video postage-stamps.
    """
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return []
    results = yolo.predict(frame_bgr, conf=YOLO_CONF, classes=[0], verbose=False)
    if not results:
        return []
    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        return []
    if save_crops_dir is not None:
        save_crops_dir.mkdir(parents=True, exist_ok=True)

    if still_relaxed:
        req_w = int(min_person_width if min_person_width is not None else 64)
        req_h = int(min_person_height if min_person_height is not None else 80)
        req_area = int(min_person_area if min_person_area is not None else 40 * 50)
        req_short = int(min_crop_short_side if min_crop_short_side is not None else 72)
        req_lap = float(min_laplacian if min_laplacian is not None else 60.0)
        req_den = float(min_denoise_laplacian if min_denoise_laplacian is not None else 18.0)
        aspect_floor = 0.85
        crop_aspect_floor = 0.70
    else:
        req_w = int(min_person_width if min_person_width is not None else MIN_PERSON_WIDTH)
        req_h = int(min_person_height if min_person_height is not None else MIN_PERSON_HEIGHT)
        req_area = int(min_person_area if min_person_area is not None else MIN_PERSON_AREA)
        req_short = int(min_crop_short_side if min_crop_short_side is not None else MIN_CROP_SHORT_SIDE)
        req_lap = float(min_laplacian if min_laplacian is not None else MIN_SHARPNESS_LAPLACIAN)
        req_den = float(min_denoise_laplacian if min_denoise_laplacian is not None else 40.0)
        aspect_floor = MIN_PERSON_ASPECT
        crop_aspect_floor = 0.95

    hits: list[FrameHit] = []
    for box in boxes:
        xyxy = box.xyxy[0].cpu().numpy()
        x1, y1, x2, y2 = map(int, xyxy)
        width, height = x2 - x1, y2 - y1
        if width <= 0 or height <= 0:
            continue
        if width * height < req_area:
            continue
        if height < req_h:
            continue
        if width < req_w:
            continue
        if (height / float(width)) < aspect_floor:
            continue
        y2b = y1 + max(int(height * 0.60), min(height, int(height * 0.80)))
        crop = frame_bgr[
            max(0, y1) : min(frame_bgr.shape[0], y2b),
            max(0, x1) : min(frame_bgr.shape[1], x2),
        ]
        if crop.size == 0:
            continue
        ch, cw = crop.shape[:2]
        if ch < req_h or cw < req_w or (ch / float(max(cw, 1))) < crop_aspect_floor:
            continue
        if is_blurry_crop(
            crop,
            min_laplacian=req_lap,
            min_short_side=req_short,
            min_denoise_laplacian=req_den,
            skip_mid_size_bands=still_relaxed,
        ):
            continue
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        score, pos_s, neg_s, cue = scorer.score_image(pil)
        thr = effective_score_threshold(crop, score_threshold)
        if score < thr:
            continue
        crop_path = None
        if save_crops_dir is not None:
            crop_path = str(save_crops_dir / f"{video_id}_{frame_idx}_{x1}_{y1}.jpg")
            pil.save(crop_path, quality=85)
        hits.append(
            FrameHit(
                video_id=video_id,
                time_sec=time_sec,
                frame_idx=frame_idx,
                score=score,
                pos_score=pos_s,
                neg_score=neg_s,
                best_cue=cue,
                bbox=[float(x1), float(y1), float(x2), float(y2)],
                crop_path=crop_path,
            )
        )
    hits.sort(key=lambda h: -h.score)
    return hits


def scan_still(
    image_path: Path,
    video_id: str,
    scorer: CueScorer,
    yolo: YOLO,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    save_crops_dir: Path | None = None,
) -> list[FrameHit]:
    """Score a single still image (SWA JPEG / photo archive).

    Uses relaxed person-size gates so group photos on archival plates can score;
    EFG video keeps the stricter postage-stamp gates.
    """
    im = cv2.imread(str(image_path))
    if im is None:
        raise RuntimeError(f"Cannot open image {image_path}")
    return score_person_crops(
        im,
        video_id=video_id,
        scorer=scorer,
        yolo=yolo,
        time_sec=0.0,
        frame_idx=0,
        score_threshold=score_threshold,
        save_crops_dir=save_crops_dir,
        still_relaxed=True,
    )
