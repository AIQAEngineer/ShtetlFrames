"""Upload trimmed clips to Google Drive (OAuth user preferred; SA needs Shared Drive)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR, ROOT

_DEFAULT_CREDS = ROOT / "secrets" / "google_drive_service_account.json"
_DEFAULT_OAUTH_CLIENT = ROOT / "secrets" / "google_drive_oauth_client.json"
_DEFAULT_TOKEN = OUTPUT_DIR / "google_drive_token.json"

SCOPES = ("https://www.googleapis.com/auth/drive.file",)


def _env(key: str, default: str = "") -> str:
    try:
        from settings_store import get_setting

        v = (get_setting(key) or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (os.environ.get(key) or default).strip()


def oauth_client_path() -> Path | None:
    raw = _env("GOOGLE_DRIVE_OAUTH_CLIENT")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        return p if p.is_file() else None
    if _DEFAULT_OAUTH_CLIENT.is_file():
        return _DEFAULT_OAUTH_CLIENT
    return None


def service_account_path() -> Path | None:
    raw = _env("GOOGLE_DRIVE_CREDENTIALS")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_file():
            try:
                if _load_creds_info(p).get("type") == "service_account":
                    return p
            except Exception:
                return p
        return None
    if _DEFAULT_CREDS.is_file():
        return _DEFAULT_CREDS
    return None


def credentials_path() -> Path | None:
    """Prefer OAuth client (personal Drive) over service account."""
    oauth = oauth_client_path()
    if oauth:
        return oauth
    # Explicit path may be either type
    raw = _env("GOOGLE_DRIVE_CREDENTIALS")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_file():
            return p
    return service_account_path() or oauth_client_path()


def folder_id() -> str:
    return _env("GOOGLE_DRIVE_FOLDER_ID")


def token_path() -> Path:
    raw = _env("GOOGLE_DRIVE_TOKEN")
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else ROOT / p
    return _DEFAULT_TOKEN


def _load_creds_info(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _auth_mode() -> str:
    path = credentials_path()
    if not path:
        return "none"
    try:
        info = _load_creds_info(path)
    except Exception:
        return "unknown"
    if info.get("type") == "service_account":
        return "service_account"
    if "installed" in info or "web" in info:
        return "oauth"
    return "unknown"


def status() -> dict[str, Any]:
    creds = credentials_path()
    folder = folder_id()
    token = token_path()
    mode = _auth_mode()
    configured = bool(folder and creds)
    hint = None
    warning = None
    if not folder:
        hint = "Set GOOGLE_DRIVE_FOLDER_ID to your Drive folder ID."
    elif mode == "service_account":
        warning = (
            "Service accounts cannot upload to personal My Drive folders. "
            "Add secrets/google_drive_oauth_client.json (Desktop OAuth) and Connect Google account, "
            "or use a Shared Drive."
        )
    elif mode == "oauth" and not token.is_file():
        hint = "OAuth client found — click Connect Google account once to sign in."
    elif not creds:
        hint = (
            "Add secrets/google_drive_oauth_client.json (Desktop OAuth client) "
            "or a Shared Drive + service account."
        )
    return {
        "ok": True,
        "configured": configured,
        "auth_mode": mode,
        "has_credentials": bool(creds),
        "credentials_path": str(creds) if creds else None,
        "has_folder_id": bool(folder),
        "folder_id": folder or None,
        "has_token": token.is_file(),
        "oauth_client": str(oauth_client_path()) if oauth_client_path() else None,
        "hint": hint,
        "warning": warning,
    }


def _build_oauth_credentials(path: Path, *, interactive: bool = True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    tok = token_path()
    creds = None
    if tok.is_file():
        creds = Credentials.from_authorized_user_file(str(tok), list(SCOPES))
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        tok.parent.mkdir(parents=True, exist_ok=True)
        tok.write_text(creds.to_json(), encoding="utf-8")
        return creds
    if creds and creds.valid:
        return creds
    if not interactive:
        raise RuntimeError("google_drive_oauth_required")
    flow = InstalledAppFlow.from_client_secrets_file(str(path), list(SCOPES))
    creds = flow.run_local_server(port=0, open_browser=True)
    tok.parent.mkdir(parents=True, exist_ok=True)
    tok.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _build_credentials(path: Path, *, interactive: bool = False):
    from google.oauth2 import service_account

    info = _load_creds_info(path)
    if info.get("type") == "service_account":
        return service_account.Credentials.from_service_account_file(
            str(path), scopes=list(SCOPES)
        )
    return _build_oauth_credentials(path, interactive=interactive)


def authorize_oauth() -> dict[str, Any]:
    """Open browser for Google sign-in; save token for uploads."""
    path = oauth_client_path()
    if not path:
        # Allow GOOGLE_DRIVE_CREDENTIALS if it's an OAuth client file
        cand = credentials_path()
        if cand and _load_creds_info(cand).get("type") != "service_account":
            path = cand
    if not path:
        raise RuntimeError(
            "oauth_client_missing: create a Desktop OAuth client in Google Cloud and save it as "
            "secrets/google_drive_oauth_client.json"
        )
    _build_oauth_credentials(path, interactive=True)
    return status()


def _drive_service(*, interactive: bool = False):
    from googleapiclient.discovery import build

    path = credentials_path()
    if not path:
        raise RuntimeError("google_drive_credentials_missing")
    if not folder_id():
        raise RuntimeError("google_drive_folder_id_missing")
    # Prefer OAuth when a token exists even if SA path is also present
    oauth = oauth_client_path()
    tok = token_path()
    if oauth and tok.is_file():
        path = oauth
    creds = _build_credentials(path, interactive=interactive)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_file(
    path: Path,
    *,
    name: str | None = None,
    folder: str | None = None,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Upload ``path`` into the configured Drive folder. Returns file metadata."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    if not path.is_file():
        raise FileNotFoundError(str(path))

    dest = (folder or folder_id()).strip()
    if not dest:
        raise RuntimeError("google_drive_folder_id_missing")

    mode = _auth_mode()
    # If only SA and no OAuth token, warn early with actionable message
    if mode == "service_account" and not (
        oauth_client_path() and token_path().is_file()
    ):
        # Still attempt (Shared Drive works); map quota error clearly below
        pass

    try:
        service = _drive_service(interactive=False)
        body: dict[str, Any] = {
            "name": name or path.name,
            "parents": [dest],
        }
        media = MediaFileUpload(
            str(path),
            mimetype=mime_type or "video/mp4",
            resumable=True,
        )
        created = (
            service.files()
            .create(
                body=body,
                media_body=media,
                fields="id,name,webViewLink,webContentLink,size,mimeType",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as e:
        msg = str(e)
        if "storageQuotaExceeded" in msg or "Service Accounts do not have storage quota" in msg:
            raise RuntimeError(
                "drive_sa_no_quota: Service accounts cannot upload to personal My Drive. "
                "Fix: (1) put an OAuth Desktop client JSON at secrets/google_drive_oauth_client.json "
                "and Connect Google account, or (2) use a Shared Drive folder and add the "
                "service account as Content manager."
            ) from e
        raise RuntimeError(f"drive_http_error: {msg[:350]}") from e

    return {
        "id": created.get("id"),
        "name": created.get("name"),
        "webViewLink": created.get("webViewLink"),
        "webContentLink": created.get("webContentLink"),
        "size": created.get("size"),
        "mimeType": created.get("mimeType"),
    }
