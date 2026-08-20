"""G3 box half: move files across the boundary, resumably, without touching a data cycle.

The appliance asks the cloud what files exist, works out what it is missing, and fetches
them a chunk at a time — recording the offset it has reached in the database so a
transfer interrupted at 80% resumes at 80%. On an intermittent link that distinction is
not an optimisation; a transfer that restarts from zero on every drop never finishes.

Everything here is bounded. One pass takes a byte budget and a file-count budget and then
stops, so a school with a decade of scanned report cards converges over many passes
instead of pinning the link. Nothing here is called by ``run_sync_cycle``: files are a
separate command and a separate task precisely so a large upload can never delay or fail
the row rail.

Verification is the point at which a transfer counts. Bytes are staged locally and the
whole file is hashed against the sender's declared sha256 BEFORE it is committed to
storage, because a truncated download that lands in storage is indistinguishable from a
good one afterwards — and would then be served to a parent as their child's report card.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

_CHUNK_BYTES = 1024 * 1024  # magic-number-allow: 1 MiB transfer chunk
_DEFAULT_BUDGET_BYTES = 32 * 1024 * 1024  # magic-number-allow: bytes per pass (32 MiB)
_DEFAULT_MAX_FILES = 25  # magic-number-allow: files per pass
_MAX_ATTEMPTS = 5  # magic-number-allow: attempts before a transfer is parked as FAILED
_STAGING_DIR = ".rmc_sync_staging"


def file_sync_enabled() -> bool:
    return bool(getattr(settings, "RMC_SYNC_FILE_TRANSFER_ENABLED", True))


def _budget_bytes() -> int:
    try:
        return max(1, int(getattr(settings, "RMC_SYNC_FILE_BUDGET_BYTES", _DEFAULT_BUDGET_BYTES)))
    except (TypeError, ValueError):
        return _DEFAULT_BUDGET_BYTES


def _max_files() -> int:
    try:
        return max(1, int(getattr(settings, "RMC_SYNC_FILE_MAX_PER_PASS", _DEFAULT_MAX_FILES)))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_FILES


def _staging_path(school_id, relative_path) -> str:
    root = getattr(settings, "MEDIA_ROOT", "") or os.path.join(
        str(getattr(settings, "BASE_DIR", ".")), "media"
    )
    digest = hashlib.sha1(f"{school_id}|{relative_path}".encode("utf-8")).hexdigest()
    folder = os.path.join(str(root), _STAGING_DIR)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{digest}.part")


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
def fetch_manifest(endpoint: str, token: str, *, entities=None, timeout: float = 30.0):
    """``(status, payload)`` from the cloud's file manifest endpoint."""
    query = {}
    ents = [str(e).strip().lower() for e in (entities or []) if str(e).strip()]
    if ents:
        query["entities"] = ",".join(ents)
    url = endpoint + (("?" + urllib.parse.urlencode(query)) if query else "")
    req = urllib.request.Request(
        url, method="GET", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator URL
            return resp.getcode(), json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8", "replace") or "{}")
        except (OSError, ValueError, AttributeError):
            return exc.code, {}


def fetch_chunk(endpoint: str, token: str, path: str, offset: int, *, length: int = _CHUNK_BYTES,
                timeout: float = 60.0):
    """``(status, bytes, meta)`` for one byte range. Connectivity failures PROPAGATE."""
    from apps.api.sync_files_api import (
        FILE_COMPLETE_HEADER,
        FILE_SHA256_HEADER,
        FILE_SIZE_HEADER,
    )

    url = endpoint + "?" + urllib.parse.urlencode(
        {"path": path, "offset": int(offset), "length": int(length)}
    )
    req = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator URL
            return (
                resp.getcode(),
                resp.read(),
                {
                    "size": int(resp.headers.get(FILE_SIZE_HEADER) or 0),
                    "sha256": (resp.headers.get(FILE_SHA256_HEADER) or "").strip(),
                    "complete": (resp.headers.get(FILE_COMPLETE_HEADER) or "") == "1",
                },
            )
    except urllib.error.HTTPError as exc:
        return exc.code, b"", {}


def send_chunk(endpoint: str, token: str, path: str, offset: int, payload: bytes,
               *, sha256: str, size: int, timeout: float = 120.0):
    """``(status, body)`` for one uploaded byte range. Connectivity failures PROPAGATE."""
    from apps.api.sync_files_api import (
        FILE_OFFSET_HEADER,
        FILE_PATH_HEADER,
        FILE_SHA256_HEADER,
        FILE_SIZE_HEADER,
    )

    req = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            FILE_PATH_HEADER: path,
            FILE_OFFSET_HEADER: str(int(offset)),
            FILE_SHA256_HEADER: sha256 or "",
            FILE_SIZE_HEADER: str(int(size)),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator URL
            return resp.getcode(), json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8", "replace") or "{}")
        except (OSError, ValueError, AttributeError):
            return exc.code, {}


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #
def enqueue_from_manifest(school, remote_files) -> dict:
    """Compare the cloud's manifest with local storage and queue what differs.

    Compares by CONTENT (sha256), not by presence: a file that exists locally but does not
    match — a half-written download from before this existed, a file replaced on the cloud
    — is re-fetched. Presence alone would leave corrupted or stale files in place forever
    while reporting a clean sync.
    """
    from apps.sync_engine.file_manifest import file_stat
    from apps.sync_engine.models import SyncFileTransfer

    queued = skipped = 0
    for entry in remote_files or []:
        path = (entry.get("path") or "").strip()
        if not path:
            continue
        remote_sha = (entry.get("sha256") or "").strip()
        _local_size, local_sha = file_stat(path)
        if local_sha and remote_sha and local_sha == remote_sha:
            skipped += 1
            continue
        SyncFileTransfer.objects.update_or_create(
            school=school,
            direction=SyncFileTransfer.PULL,
            relative_path=path,
            defaults={
                "sha256": remote_sha,
                "size_bytes": int(entry.get("size") or 0),
                "entity_type": (entry.get("entity_type") or "")[:64],
                "local_pk": str(entry.get("id") or "")[:64],
                "field_name": (entry.get("field") or "")[:64],
                # Re-queueing a DONE row whose hash no longer matches is the point of
                # comparing by content; leaving it DONE would freeze the stale copy.
                "state": SyncFileTransfer.State.PENDING,
            },
        )
        queued += 1
    return {"queued": queued, "already_current": skipped}


def enqueue_local_only(school, remote_files) -> dict:
    """Queue for UPLOAD every local file the cloud does not hold with the same hash."""
    from apps.sync_engine.file_manifest import build_manifest
    from apps.sync_engine.models import SyncFileTransfer

    remote = {
        (f.get("path") or ""): (f.get("sha256") or "") for f in (remote_files or [])
    }
    queued = 0
    for entry in build_manifest(school):
        path = entry["path"]
        if remote.get(path) and remote[path] == entry["sha256"]:
            continue
        SyncFileTransfer.objects.update_or_create(
            school=school,
            direction=SyncFileTransfer.PUSH,
            relative_path=path,
            defaults={
                "sha256": entry["sha256"],
                "size_bytes": int(entry["size"] or 0),
                "entity_type": entry["entity_type"][:64],
                "local_pk": str(entry["id"])[:64],
                "field_name": entry["field"][:64],
                "state": SyncFileTransfer.State.PENDING,
            },
        )
        queued += 1
    return {"queued": queued}


# --------------------------------------------------------------------------- #
# Workers
# --------------------------------------------------------------------------- #
def _park(transfer, message):
    transfer.attempts += 1
    transfer.last_error = str(message)[:255]
    # Parked, not deleted. A FAILED row is the record an operator needs in order to see
    # that a file is stuck; silently dropping it would present a broken sync as a clean one.
    transfer.state = (
        transfer.State.FAILED if transfer.attempts >= _MAX_ATTEMPTS else transfer.State.PENDING
    )
    # bytes_done is persisted here too. A caller that has just discarded a corrupted
    # staging copy sets it back to 0 immediately before parking, and leaving it out of
    # update_fields would keep the DURABLE offset pointing at bytes that no longer exist -
    # so the operator surface would report progress the transfer does not have.
    transfer.save(
        update_fields=["attempts", "last_error", "state", "bytes_done", "updated_at"]
    )


def download_one(transfer, endpoint, token) -> tuple[bool, str]:
    """Fetch one queued file to completion, resuming from ``bytes_done``."""
    staged = _staging_path(transfer.school_id, transfer.relative_path)
    have = os.path.getsize(staged) if os.path.exists(staged) else 0
    if have != transfer.bytes_done:
        # The durable offset and the staged file disagree (a crash mid-write, or a staging
        # dir wiped). Trust the FILE - it is the thing the next request must append to.
        transfer.bytes_done = have
    transfer.state = transfer.State.ACTIVE
    transfer.save(update_fields=["state", "bytes_done", "updated_at"])

    declared_sha = transfer.sha256
    while True:
        status, payload, meta = fetch_chunk(endpoint, token, transfer.relative_path, have)
        if status != 200:
            _park(transfer, f"HTTP {status} fetching offset {have}")
            return False, f"HTTP {status}"
        if payload:
            with open(staged, "ab") as fh:
                fh.write(payload)
            have += len(payload)
            transfer.bytes_done = have
            transfer.save(update_fields=["bytes_done", "updated_at"])
        declared_sha = declared_sha or meta.get("sha256") or ""
        total = int(meta.get("size") or transfer.size_bytes or 0)
        if meta.get("complete") or (total and have >= total) or not payload:
            break

    digest = hashlib.sha256()
    with open(staged, "rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK_BYTES), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if not declared_sha:
        # Nothing to verify AGAINST. Committing anyway would let a truncated or empty
        # transfer overwrite a real file with no way to tell afterwards - the exact
        # outcome the hash check exists to prevent. Park it: the manifest carries a
        # sha256 for every file it offers, so a missing one means something upstream is
        # wrong, and that is worth reporting rather than papering over.
        os.remove(staged)
        transfer.bytes_done = 0
        _park(transfer, "the sender declared no sha256; refusing to commit unverified bytes")
        return False, "unverifiable"
    if actual != declared_sha:
        # Never commit an unverified file. Discard the staging copy so the next pass
        # starts clean rather than resuming on top of corrupted bytes.
        os.remove(staged)
        transfer.bytes_done = 0
        _park(transfer, f"hash mismatch (expected {declared_sha[:12]}, got {actual[:12]})")
        return False, "hash_mismatch"

    with open(staged, "rb") as fh:
        content = fh.read()
    if default_storage.exists(transfer.relative_path):
        default_storage.delete(transfer.relative_path)
    default_storage.save(transfer.relative_path, ContentFile(content))
    os.remove(staged)
    transfer.state = transfer.State.DONE
    transfer.sha256 = actual
    transfer.last_error = ""
    transfer.save(update_fields=["state", "sha256", "last_error", "updated_at"])
    return True, ""


def upload_one(transfer, endpoint, token) -> tuple[bool, str]:
    """Send one queued file to completion, resuming from the cloud's reported offset."""
    from apps.sync_engine.file_manifest import file_stat

    size, sha = file_stat(transfer.relative_path)
    if not size:
        _park(transfer, "the local file is missing")
        return False, "missing_local_file"
    transfer.state = transfer.State.ACTIVE
    transfer.size_bytes, transfer.sha256 = size, sha
    transfer.save(update_fields=["state", "size_bytes", "sha256", "updated_at"])

    offset = int(transfer.bytes_done or 0)
    with default_storage.open(transfer.relative_path, "rb") as fh:
        while offset < size:
            fh.seek(offset)
            payload = fh.read(_CHUNK_BYTES)
            if not payload:
                break
            status, body = send_chunk(
                endpoint, token, transfer.relative_path, offset, payload, sha256=sha, size=size
            )
            if status == 409 and "expected_offset" in (body or {}):
                # The cloud already holds part of this file. Believe IT and continue from
                # there rather than restarting - that is the whole point of resumability.
                offset = int(body["expected_offset"])
                transfer.bytes_done = offset
                transfer.save(update_fields=["bytes_done", "updated_at"])
                continue
            if status != 200 or not (body or {}).get("ok"):
                _park(transfer, f"HTTP {status} at offset {offset}: {str(body)[:80]}")
                return False, f"HTTP {status}"
            offset += len(payload)
            transfer.bytes_done = offset
            transfer.save(update_fields=["bytes_done", "updated_at"])
            if (body or {}).get("complete"):
                break
    transfer.state = transfer.State.DONE
    transfer.last_error = ""
    transfer.save(update_fields=["state", "last_error", "updated_at"])
    return True, ""


def run_file_sync_pass(school, *, manifest_endpoint, chunk_endpoint, token,
                       push=True, pull=True) -> dict:
    """One bounded pass: refresh the manifest, then move what fits in the budget.

    NEVER RAISES. Files are a background concern; a failure here must show up as a report,
    not as an exception that takes down whatever scheduled it.
    """
    from apps.sync_engine.models import SyncFileTransfer

    result = {
        "ok": False, "enqueued": 0, "downloaded": 0, "uploaded": 0,
        "bytes": 0, "failed": 0, "message": "", "errors": [],
    }
    if not file_sync_enabled():
        result["message"] = "file sync is disabled on this deployment"
        return result
    try:
        status, payload = fetch_manifest(manifest_endpoint, token)
        if status != 200 or not payload.get("ok"):
            result["errors"].append(f"manifest unavailable (HTTP {status})")
            result["message"] = "could not read the cloud file manifest"
            return result
        remote_files = payload.get("files") or []
        if pull:
            result["enqueued"] += enqueue_from_manifest(school, remote_files)["queued"]
        if push:
            result["enqueued"] += enqueue_local_only(school, remote_files)["queued"]

        budget, max_files = _budget_bytes(), _max_files()
        spent = moved = 0
        pending = SyncFileTransfer.objects.filter(
            school=school, state__in=[SyncFileTransfer.State.PENDING, SyncFileTransfer.State.ACTIVE]
        ).order_by("size_bytes", "created_at")
        for transfer in pending:
            if moved >= max_files or spent >= budget:
                # Stopping mid-queue is normal, not a failure: durable offsets mean the
                # next pass resumes exactly here.
                result["message"] = f"budget reached; {moved} file(s) this pass"
                break
            before = int(transfer.bytes_done or 0)
            try:
                if transfer.direction == SyncFileTransfer.PULL:
                    ok, err = download_one(transfer, chunk_endpoint, token)
                    if ok:
                        result["downloaded"] += 1
                else:
                    ok, err = upload_one(transfer, chunk_endpoint, token)
                    if ok:
                        result["uploaded"] += 1
            except Exception as exc:  # noqa: BLE001 - offline mid-file is the normal case
                _park(transfer, str(exc))
                ok, err = False, str(exc)
            transfer.refresh_from_db(fields=["bytes_done"])
            spent += max(0, int(transfer.bytes_done or 0) - before)
            moved += 1
            if not ok:
                result["failed"] += 1
                result["errors"].append(f"{transfer.relative_path}: {err}")
        result["bytes"] = spent
        result["ok"] = not result["errors"]
        result["message"] = result["message"] or (
            f"{result['downloaded']} down, {result['uploaded']} up, "
            f"{result['bytes']} byte(s)"
        )
    except Exception as exc:  # noqa: BLE001 - the pass reports, it does not raise
        result["errors"].append(str(exc))
        result["message"] = "file sync pass failed"
    return result


__all__ = [
    "download_one",
    "enqueue_from_manifest",
    "enqueue_local_only",
    "fetch_chunk",
    "fetch_manifest",
    "file_sync_enabled",
    "run_file_sync_pass",
    "send_chunk",
    "upload_one",
]
