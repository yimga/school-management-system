"""OAuth-folder intake — Google Drive / OneDrive / Dropbox folder hand-off.

Expects a handle dict::

    {
        "provider": "google_drive" | "onedrive" | "dropbox",
        "folder_id": str,                # provider-specific folder identifier
        "access_token": str,             # short-lived OAuth token
        "recursive": bool,               # default True; one-level traversal
    }

For each file in the folder, downloads bytes to a temp file and emits an
``ArtifactPayload``. The orchestrator profiles + classifies each as usual.

Provider clients are lazily imported — installing the provider SDK is
optional. If the SDK isn't installed, this adapter raises an
``IntakeError`` with a clear install hint; the wizard surface this to
the operator who can fall back to ZIP upload.

Safety:
    * Honors ``migration_cloud.intake.max_artifact_bytes`` per file.
    * Refuses to fetch more than ``migration_cloud.intake.max_archive_members``
      files per folder (re-uses the archive cap for symmetry).
"""

from __future__ import annotations

import logging
import os
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud import defaults as mc_defaults
from apps.migration_cloud.models import IntakeMethod

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
)

logger = logging.getLogger(__name__)


class OauthFolderIntakeAdapter(IntakeAdapter):
    """Walks an OAuth-shared folder and emits one ArtifactPayload per file."""

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        if not isinstance(handle, dict):
            raise IntakeError("OAuth folder intake handle must be a dict.")
        provider = (handle.get("provider") or "").strip().lower()
        if provider not in ("google_drive", "onedrive", "dropbox"):
            raise IntakeError(
                f"Unsupported OAuth provider {provider!r}; expected google_drive/onedrive/dropbox."
            )
        if not handle.get("folder_id"):
            raise IntakeError("OAuth folder intake handle missing 'folder_id'.")
        if not handle.get("access_token"):
            raise IntakeError("OAuth folder intake handle missing 'access_token'.")

    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        provider = (handle.get("provider") or "").strip().lower()
        if provider == "google_drive":
            yield from self._iter_google_drive(handle)
        elif provider == "onedrive":
            yield from self._iter_onedrive(handle)
        elif provider == "dropbox":
            yield from self._iter_dropbox(handle)

    # --- Google Drive ------------------------------------------------------

    def _iter_google_drive(self, handle: dict[str, Any]) -> Iterator[ArtifactPayload]:
        try:
            from googleapiclient.discovery import build  # type: ignore[import-not-found]
            from google.oauth2.credentials import Credentials  # type: ignore[import-not-found]
        except ImportError as exc:
            raise IntakeError(
                "Google Drive intake requires 'google-api-python-client' + "
                "'google-auth' — install before using google_drive handles."
            ) from exc

        creds = Credentials(token=handle["access_token"])
        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        max_members = int(mc_defaults.get("migration_cloud.intake.max_archive_members"))
        max_bytes = int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))
        folder_id = handle["folder_id"]

        page_token = None
        emitted = 0
        while True:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                pageSize=200,
            ).execute()
            for f in resp.get("files", []):
                if emitted >= max_members:
                    return
                if f.get("mimeType") == "application/vnd.google-apps.folder":
                    continue  # one-level only; recursive=True deferred until needed
                size = int(f.get("size", 0) or 0)
                if size and size > max_bytes:
                    raise IntakeError(
                        f"Drive file {f.get('name')} is {size:,} bytes; exceeds cap."
                    )
                payload = _download_drive_file(service, f, max_bytes)
                if payload is not None:
                    yield payload
                    emitted += 1
            page_token = resp.get("nextPageToken")
            if not page_token:
                return

    # --- OneDrive ----------------------------------------------------------

    def _iter_onedrive(self, handle: dict[str, Any]) -> Iterator[ArtifactPayload]:
        """Microsoft Graph drive-children walk → temp-file downloads.

        The handle's ``access_token`` is a Microsoft Graph token (delegated
        Files.Read). ``folder_id`` is the Graph item id of the folder root
        (use ``"root"`` for the user's OneDrive root). Optional
        ``drive_id`` selects a specific drive (SharePoint document
        library) — defaults to the user's personal drive.
        """
        try:
            import requests  # type: ignore[import-not-found]
        except ImportError as exc:
            raise IntakeError(
                "OneDrive intake requires the 'requests' library."
            ) from exc

        access_token = handle["access_token"]
        folder_id = handle["folder_id"]
        drive_id = handle.get("drive_id")  # optional
        max_members = int(mc_defaults.get("migration_cloud.intake.max_archive_members"))
        max_bytes = int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))

        base = "https://graph.microsoft.com/v1.0"
        if drive_id:
            children_url = f"{base}/drives/{drive_id}/items/{folder_id}/children"
        else:
            children_url = f"{base}/me/drive/items/{folder_id}/children"

        headers = {"Authorization": f"Bearer {access_token}"}
        emitted = 0
        next_url = children_url
        while next_url:
            resp = requests.get(next_url, headers=headers, timeout=30)
            if not resp.ok:
                raise IntakeError(
                    f"OneDrive list failed [{resp.status_code}]: {resp.text[:200]}"
                )
            data = resp.json() if resp.content else {}
            for f in data.get("value", []) or []:
                if emitted >= max_members:
                    return
                if f.get("folder") is not None:
                    continue  # one-level only
                size = int(f.get("size", 0) or 0)
                if size and size > max_bytes:
                    raise IntakeError(
                        f"OneDrive file {f.get('name')} is {size:,} bytes; exceeds cap."
                    )
                download_url = (
                    f.get("@microsoft.graph.downloadUrl")
                    or f.get("@content.downloadUrl")
                )
                if not download_url:
                    item_id = f.get("id")
                    download_url = f"{base}/me/drive/items/{item_id}/content"
                    payload = _download_via_url(
                        download_url,
                        name=f.get("name") or "onedrive_file",
                        mime=f.get("file", {}).get("mimeType") or "",
                        max_bytes=max_bytes,
                        headers=headers,
                    )
                else:
                    payload = _download_via_url(
                        download_url,
                        name=f.get("name") or "onedrive_file",
                        mime=f.get("file", {}).get("mimeType") or "",
                        max_bytes=max_bytes,
                    )
                if payload is not None:
                    yield payload
                    emitted += 1
            next_url = data.get("@odata.nextLink")

    # --- Dropbox -----------------------------------------------------------

    def _iter_dropbox(self, handle: dict[str, Any]) -> Iterator[ArtifactPayload]:
        """Dropbox ``files/list_folder`` walk → temp-file downloads.

        ``folder_id`` is a Dropbox path (``"/path/to/folder"``) or path-id
        (``"id:abc123"``). Uses the official ``dropbox`` Python SDK when
        installed; degrades to direct HTTP otherwise.
        """
        access_token = handle["access_token"]
        folder_path = handle["folder_id"]
        max_members = int(mc_defaults.get("migration_cloud.intake.max_archive_members"))
        max_bytes = int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))

        # Preferred: official SDK (handles pagination, retries, OAuth refresh).
        try:
            import dropbox  # type: ignore[import-not-found]
            from dropbox.files import FileMetadata  # type: ignore[import-not-found]
        except ImportError:
            yield from self._iter_dropbox_http(
                access_token, folder_path, max_members, max_bytes,
            )
            return

        dbx = dropbox.Dropbox(access_token)
        emitted = 0
        result = dbx.files_list_folder(path=folder_path or "", recursive=False)
        while True:
            for entry in result.entries:
                if emitted >= max_members:
                    return
                if not isinstance(entry, FileMetadata):
                    continue
                if entry.size and entry.size > max_bytes:
                    raise IntakeError(
                        f"Dropbox file {entry.name} is {entry.size:,} bytes; exceeds cap."
                    )
                _meta, response = dbx.files_download(entry.path_lower)
                payload = _materialize_payload(
                    name=entry.name,
                    iter_chunks=lambda r=response: r.iter_content(chunk_size=1024 * 1024),
                    mime="",
                    max_bytes=max_bytes,
                )
                if payload is not None:
                    yield payload
                    emitted += 1
            if not result.has_more:
                return
            result = dbx.files_list_folder_continue(result.cursor)

    def _iter_dropbox_http(
        self,
        access_token: str,
        folder_path: str,
        max_members: int,
        max_bytes: int,
    ) -> Iterator[ArtifactPayload]:
        """Dropbox v2 HTTP fallback when the SDK isn't installed."""
        try:
            import json as _json
            import requests  # type: ignore[import-not-found]
        except ImportError as exc:
            raise IntakeError(
                "Dropbox intake requires either the 'dropbox' SDK or 'requests'."
            ) from exc

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        list_url = "https://api.dropboxapi.com/2/files/list_folder"
        cont_url = "https://api.dropboxapi.com/2/files/list_folder/continue"

        body = {"path": folder_path or "", "recursive": False}
        resp = requests.post(list_url, headers=headers, data=_json.dumps(body), timeout=30)
        if not resp.ok:
            raise IntakeError(
                f"Dropbox list failed [{resp.status_code}]: {resp.text[:200]}"
            )
        cursor = resp.json().get("cursor")
        emitted = 0
        while True:
            data = resp.json() if resp.content else {}
            for entry in data.get("entries", []):
                if emitted >= max_members:
                    return
                if entry.get(".tag") != "file":
                    continue
                size = int(entry.get("size", 0) or 0)
                if size and size > max_bytes:
                    raise IntakeError(
                        f"Dropbox file {entry.get('name')} is {size:,} bytes; exceeds cap."
                    )
                dl_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Dropbox-API-Arg": _json.dumps({"path": entry["path_lower"]}),
                }
                dl_resp = requests.post(
                    "https://content.dropboxapi.com/2/files/download",
                    headers=dl_headers, timeout=120, stream=True,
                )
                if not dl_resp.ok:
                    continue
                payload = _materialize_payload(
                    name=entry.get("name") or "dropbox_file",
                    iter_chunks=lambda r=dl_resp: r.iter_content(chunk_size=1024 * 1024),
                    mime="",
                    max_bytes=max_bytes,
                )
                if payload is not None:
                    yield payload
                    emitted += 1
            if not data.get("has_more") or not cursor:
                return
            resp = requests.post(
                cont_url, headers=headers, data=_json.dumps({"cursor": cursor}), timeout=30,
            )
            if not resp.ok:
                return
            cursor = resp.json().get("cursor")


def _download_drive_file(service, file_meta: dict[str, Any], max_bytes: int) -> ArtifactPayload | None:
    """Stream a Drive file to a temp file; return ``ArtifactPayload`` or ``None``."""
    try:
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore[import-not-found]
    except ImportError:
        return None

    file_id = file_meta.get("id")
    name = file_meta.get("name") or "drive_file"
    fd, tmp_name = tempfile.mkstemp(prefix="mc_drive_", suffix=f"_{_safe(name)}")
    os.close(fd)
    tmp = Path(tmp_name)

    request = service.files().get_media(fileId=file_id)
    total = 0
    digest = sha256()
    with tmp.open("wb") as out:
        downloader = MediaIoBaseDownload(out, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
            if tmp.stat().st_size > max_bytes:
                raise IntakeError(
                    f"Drive download for {name} exceeded artifact cap."
                )
    # Hash after writing — Drive API doesn't expose a hash for arbitrary files.
    with tmp.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
            total += len(chunk)

    def opener(p=tmp):
        return p.open("rb")

    return ArtifactPayload(
        path_within_bundle=name,
        filename=name,
        byte_size=total,
        sha256=digest.hexdigest(),
        mime_type=file_meta.get("mimeType") or "",
        content_opener=opener,
    )


def _safe(name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_\-.]+", "_", name).strip("_") or "file"


def _materialize_payload(
    *,
    name: str,
    iter_chunks,
    mime: str,
    max_bytes: int,
) -> ArtifactPayload | None:
    """Stream chunks into a temp file, compute sha256, return ArtifactPayload.

    Reused by OneDrive + Dropbox (and any future provider whose SDK returns
    a streaming response object).
    """
    fd, tmp_name = tempfile.mkstemp(prefix="mc_oauth_", suffix=f"_{_safe(name)}")
    os.close(fd)
    tmp = Path(tmp_name)
    total = 0
    digest = sha256()
    try:
        with tmp.open("wb") as out:
            for chunk in iter_chunks():
                if not chunk:
                    continue
                out.write(chunk)
                digest.update(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise IntakeError(
                        f"OAuth download for {name} exceeded artifact cap."
                    )
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        raise

    def opener(p=tmp):
        return p.open("rb")

    return ArtifactPayload(
        path_within_bundle=name,
        filename=name,
        byte_size=total,
        sha256=digest.hexdigest(),
        mime_type=mime,
        content_opener=opener,
    )


def _download_via_url(
    url: str,
    *,
    name: str,
    mime: str,
    max_bytes: int,
    headers: dict | None = None,
) -> ArtifactPayload | None:
    """Generic GET → temp-file → ArtifactPayload helper used by OneDrive."""
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return None
    resp = requests.get(url, headers=headers or {}, timeout=120, stream=True)
    if not resp.ok:
        return None
    return _materialize_payload(
        name=name,
        iter_chunks=lambda: resp.iter_content(chunk_size=1024 * 1024),
        mime=mime,
        max_bytes=max_bytes,
    )


# Re-register over the Phase U1 stub.
register_adapter(IntakeMethod.OAUTH_FOLDER, OauthFolderIntakeAdapter())
