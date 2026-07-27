"""Image upload stub — Catbox is disabled; Review stills are local only."""

from __future__ import annotations

from pathlib import Path

USER_AGENT = "ShtetlFrames/1.0 (research; image upload)"


def upload_image(path: Path, *, user_agent: str = USER_AGENT) -> str | None:
    """No-op. Stills are saved under ``output/contact_sheets/`` on the PC.

    Kept for API compatibility with older worker/local callers.
    """
    del path, user_agent
    return None
