"""Quality gates — skip CLIP / drop segments that are soft or tiny.

Laplacian alone is fooled by film grain and upscaled pixel edges on soft EFG
crops. We combine:
  1. absolute size (tiny person boxes / postage-stamp crops)
  2. denoise-then-Laplacian (kills pixel noise, keeps real edges)
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from shtetl_core.cues import MIN_SHARPNESS_LAPLACIAN


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
    min_short_side: int = 96,
    min_denoise_laplacian: float = 28.0,
) -> bool:
    """True when the crop is too soft or too small to score.

    Soft EFG stills are often tiny (40–80px) with high raw Laplacian from
    pixel noise; denoise Laplacian + min size catches those.
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
    # Medium EFG frames: grain can push denoise Lap into the high-20s/30s while
    # still looking soft; require more when the still isn't Pathé-sized.
    if short < 400 and den < 40.0:
        return True
    # Very soft even if large enough for denoise gate edge cases.
    if crop_laplacian_var(gray) < float(min_laplacian) * 0.35:
        return True
    return False


def still_path_is_poor(path: str | Path) -> bool:
    """True when a saved Review still should not become a candidate."""
    p = Path(path)
    if not p.is_file():
        return True
    im = cv2.imread(str(p))
    if im is None:
        return True
    return is_blurry_crop(im, min_short_side=96, min_denoise_laplacian=28.0)
