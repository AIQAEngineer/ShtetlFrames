"""Cheap sharpness gate — skip CLIP scoring on blurry / soft person crops."""

from __future__ import annotations

import cv2
import numpy as np

from shtetl_core.cues import MIN_SHARPNESS_LAPLACIAN


def crop_laplacian_var(bgr_or_gray: np.ndarray, *, norm_side: int = 256) -> float:
    """Laplacian variance after normalizing max side (resolution-stable)."""
    if bgr_or_gray is None or getattr(bgr_or_gray, "size", 0) < 64:
        return 0.0
    im = np.squeeze(bgr_or_gray)
    if im.ndim == 3:
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    elif im.ndim == 2:
        gray = im
    else:
        return 0.0
    h, w = gray.shape[:2]
    if h < 8 or w < 8:
        return 0.0
    scale = float(norm_side) / float(max(h, w))
    if scale < 1.0:
        gray = cv2.resize(
            gray,
            (max(8, int(w * scale)), max(8, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def is_blurry_crop(
    bgr_or_gray: np.ndarray,
    *,
    min_laplacian: float = MIN_SHARPNESS_LAPLACIAN,
) -> bool:
    """True when the crop is too soft to score (motion blur / tiny upscales)."""
    return crop_laplacian_var(bgr_or_gray) < float(min_laplacian)
