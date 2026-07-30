"""Cloud image hosts disabled — Review stills are persisted locally only.

Implementation lives in ``shtetl_core.upload``; this module re-exports it for
backwards compatibility with older imports.
"""

from __future__ import annotations

from shtetl_core.upload import upload_image

__all__ = ["upload_image"]
