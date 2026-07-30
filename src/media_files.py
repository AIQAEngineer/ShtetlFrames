"""Shared media-file helpers: one extension set + one video lookup."""

from __future__ import annotations

from pathlib import Path

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".ogv", ".mpg", ".mpeg"}


def find_video_file(videos_dir: Path, video_id: str) -> Path | None:
    """Exact-stem match first, then substring match, among video files."""
    if not videos_dir.exists():
        return None
    for p in videos_dir.iterdir():
        if p.stem == video_id and p.suffix.lower() in VIDEO_EXTS:
            return p
    for p in videos_dir.iterdir():
        if video_id in p.stem and p.suffix.lower() in VIDEO_EXTS:
            return p
    return None
