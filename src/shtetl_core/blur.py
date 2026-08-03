"""Quality gates — skip CLIP / drop segments that are soft or tiny.

Laplacian alone is fooled by film grain and upscaled pixel edges on soft EFG
crops. We combine:
  1. absolute size (primary — gallery stills under ~200px look unusable)
  2. denoise-then-Laplacian (kills pixel noise, keeps real edges)
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from shtetl_core.cues import DEFAULT_SCORE_THRESHOLD, MIN_SHARPNESS_LAPLACIAN

try:
    from shtetl_core.cues import HQ_SCORE_THRESHOLD as _HQ_SCORE_THRESHOLD
except ImportError:  # half-synced pod: old cues.py
    _HQ_SCORE_THRESHOLD = 0.04


def _as_gray(bgr_or_gray: np.ndarray) -> np.ndarray | None:
    if bgr_or_gray is None or getattr(bgr_or_gray, "size", 0) < 64:
        return None
    im = np.squeeze(bgr_or_gray)
    if im.ndim == 3:
        return cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    if im.ndim == 2:
        return im
    return None


def _normalize(gray: np.ndarray, norm_side: int = 256) -> np.ndarray:
    h, w = gray.shape[:2]
    scale = float(norm_side) / float(max(h, w))
    if scale >= 1.0:
        return gray
    return cv2.resize(
        gray,
        (max(8, int(w * scale)), max(8, int(h * scale))),
        interpolation=cv2.INTER_AREA,
    )


def crop_laplacian_var(bgr_or_gray: np.ndarray, *, norm_side: int = 256) -> float:
    """Raw Laplacian variance (legacy); prefer denoise_laplacian_var for gating."""
    gray = _as_gray(bgr_or_gray)
    if gray is None:
        return 0.0
    h, w = gray.shape[:2]
    if h < 8 or w < 8:
        return 0.0
    g = _normalize(gray, norm_side=norm_side)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def denoise_laplacian_var(bgr_or_gray: np.ndarray, *, norm_side: int = 256) -> float:
    """Laplacian after mild Gaussian blur — ignores pixelation 'false edges'."""
    gray = _as_gray(bgr_or_gray)
    if gray is None:
        return 0.0
    h, w = gray.shape[:2]
    if h < 8 or w < 8:
        return 0.0
    g = _normalize(gray, norm_side=norm_side)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def is_blurry_crop(
    bgr_or_gray: np.ndarray,
    *,
    min_laplacian: float = MIN_SHARPNESS_LAPLACIAN,
    min_short_side: int = 240,
    min_denoise_laplacian: float = 40.0,
    skip_mid_size_bands: bool = False,
) -> bool:
    """True when the crop is too soft or too small to score.

    Soft EFG stills are often ~120–220px postage stamps with high raw Laplacian
    from grain/pixel edges. Size is the primary gate (usable Pathé stills are
    typically 600px+); denoise Laplacian catches medium soft frames.

    ``skip_mid_size_bands``: for archival stills (SWA) where people are smaller
    in a sharp plate — only enforce absolute size + denoise floor.
    """
    gray = _as_gray(bgr_or_gray)
    if gray is None:
        return True
    h, w = gray.shape[:2]
    short = min(h, w)
    if short < int(min_short_side):
        return True
    den = denoise_laplacian_var(gray)
    if den < float(min_denoise_laplacian):
        return True
    if not skip_mid_size_bands:
        # Sub-HD stills / EFG person crops: grain + watermarks inflate denoise Lap
        # while faces/coats stay soft in Review. Pathé full frames (~684px) skip.
        if short < 360 and den < 80.0:
            return True
        if short < 520 and den < 100.0:
            return True
    # Very soft even if large enough for denoise gate edge cases.
    if crop_laplacian_var(gray) < float(min_laplacian) * 0.35:
        return True
    return False


def is_high_quality_crop(
    bgr_or_gray: np.ndarray,
    *,
    min_short_side: int = 400,
    min_denoise_laplacian: float = 100.0,
) -> bool:
    """True for sharp, large crops that can use a lower CLIP score gate.

    Soft EFG postage stamps often clear the blur floor (~240px / denoise 40) but
    still produce noisy borderline CLIP scores. Only relax the score threshold
    when size + denoise Lap clearly beat that floor (Pathé-class stills).
    """
    if is_blurry_crop(bgr_or_gray):
        return False
    gray = _as_gray(bgr_or_gray)
    if gray is None:
        return False
    h, w = gray.shape[:2]
    if min(h, w) < int(min_short_side):
        return False
    return denoise_laplacian_var(gray) >= float(min_denoise_laplacian)


def effective_score_threshold(
    bgr_or_gray: np.ndarray,
    base_threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> float:
    """Lower CLIP gate for high-quality crops; otherwise keep base."""
    thr = float(base_threshold)
    if is_high_quality_crop(bgr_or_gray):
        return min(thr, float(_HQ_SCORE_THRESHOLD))
    return thr


def still_path_is_poor(path: str | Path) -> bool:
    """True when a saved Review still should not become a candidate.

    Wide collage-height sheets are split into tiles so soft panels cannot hide
    behind sheet width. Single crops use a strict size + denoise gate.
    """
    p = Path(path)
    if not p.is_file():
        return True
    im = cv2.imread(str(p))
    if im is None:
        return True
    h, w = im.shape[:2]
    # EFG multi-thumb sheets are hstacked person crops at ~200–360px tall.
    # Pathé full frames (~684px) must not be split.
    if 160 <= h <= 400 and w >= int(h * 1.05):
        n = max(2, min(4, int(round(w / float(max(h, 1))))))
        tw = max(1, w // n)
        for i in range(n):
            tile = im[:, i * tw : (i + 1) * tw]
            # Collage panels are often soft EFG postage stamps side-by-side;
            # require a larger short side than a single native crop.
            if is_blurry_crop(tile, min_short_side=280, min_denoise_laplacian=40.0):
                return True
        return False
    return is_blurry_crop(im, min_short_side=240, min_denoise_laplacian=40.0)
