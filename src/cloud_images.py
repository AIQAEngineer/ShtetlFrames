"""Cloud image hosts disabled — Review stills are persisted locally only."""

from __future__ import annotations

from pathlib import Path


def upload_image(path: Path) -> str | None:
    """No-op (Catbox removed). Local pipeline keeps ``_local_still`` bytes."""
    del path
    return None
