"""G3 cloud half: a resumable, hash-verified file channel that never touches the row rail.

A delta bundle carries column values, never bytes, so ``_derive_sync_fields`` drops every
``FileField`` — correctly, because a synced path would point the far side at a file it
does not have and the apply would report a clean 200 over a broken reference. The
consequence, until now, was that student photos, scanned report cards and payment proofs
did not exist across the boundary at all.

Three endpoints, deliberately separate from the bundle endpoints so a 50 MB scan on a
village link can never delay or fail a data cycle:

  * ``GET  files/manifest/`` — what this school has, with size and sha256.
  * ``GET  files/chunk/``    — a byte range, so a dropped connection resumes at the offset
    it reached instead of starting over.
  * ``POST files/chunk/``    — the same, upward; the cloud stages the bytes and only
    commits them to storage once the whole file hashes to what the sender declared.

AUTHORISATION. Both chunk endpoints take a storage path, which is a directory-traversal
hole unless something constrains it. Sanitising the string is the weak answer. The strong
answer, used here, is that a path is only servable when it is the current value of a
``FileField`` on a row belonging to THIS school (``file_manifest.servable_paths``). That
cannot be argued into ``../../secrets`` and cannot reach another tenant's media either.
"""
from __future__ import annotations

import hashlib
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.edge_auth import EdgeCredentialAuthentication
from apps.schools.tenant_api_guards import user_may_operate_on_school
from apps.sync_engine.file_manifest import build_manifest, file_stat, servable_paths

# Headers the box reads/sets. Kept as constants so the two sides cannot drift.
FILE_PATH_HEADER = "X-RMC-File-Path"
FILE_OFFSET_HEADER = "X-RMC-File-Offset"
FILE_SHA256_HEADER = "X-RMC-File-Sha256"
FILE_SIZE_HEADER = "X-RMC-File-Size"
FILE_COMPLETE_HEADER = "X-RMC-File-Complete"

_DEFAULT_CHUNK_BYTES = 1024 * 1024  # magic-number-allow: 1 MiB default chunk
_MAX_CHUNK_BYTES = 8 * 1024 * 1024  # magic-number-allow: 8 MiB hard ceiling per request
_DEFAULT_MANIFEST_LIMIT = 2000  # magic-number-allow: manifest entries per response
_STAGING_DIR = ".rmc_sync_staging"


def max_file_bytes() -> int:
    """Refuse absurd uploads outright. 0 disables the ceiling."""
    try:
        return max(0, int(getattr(settings, "RMC_SYNC_FILE_MAX_BYTES", 200 * 1024 * 1024)))
    except (TypeError, ValueError):
        return 200 * 1024 * 1024


def file_sync_enabled() -> bool:
    return bool(getattr(settings, "RMC_SYNC_FILE_TRANSFER_ENABLED", True))


def staging_path(school_id, relative_path) -> str:
    """A deterministic local staging file for a partial upload.

    Deterministic on purpose: a transfer interrupted by a restart has to find the bytes
    it already received, and a random temp name would silently restart every resume at
    zero — which on an intermittent link means the file never arrives at all.
    """
    root = getattr(settings, "MEDIA_ROOT", "") or os.path.join(
        str(getattr(settings, "BASE_DIR", ".")), "media"
    )
    digest = hashlib.sha1(f"{school_id}|{relative_path}".encode("utf-8")).hexdigest()
    folder = os.path.join(str(root), _STAGING_DIR)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{digest}.part")


class _EdgeFileView(APIView):
    authentication_classes = [EdgeCredentialAuthentication]
    permission_classes = [IsAuthenticated]

    def _school(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return None, Response({"ok": False, "error": "school_required"}, status=403)
        if not user_may_operate_on_school(request, school):
            return None, Response({"ok": False, "error": "forbidden"}, status=403)
        if not file_sync_enabled():
            return None, Response({"ok": False, "error": "file_sync_disabled"}, status=409)
        return school, None


@extend_schema_view(
    get=extend_schema(
        tags=["Offline Sync"],
        summary="List this school's stored files with hashes",
        responses={200: dict, 403: dict},
    ),
)
class SyncFileManifestView(_EdgeFileView):
    def get(self, request):
        school, refusal = self._school(request)
        if refusal is not None:
            return refusal
        entities = [
            e.strip().lower()
            for e in (request.query_params.get("entities") or "").split(",")
            if e.strip()
        ]
        try:
            limit = min(int(request.query_params.get("limit") or _DEFAULT_MANIFEST_LIMIT),
                        _DEFAULT_MANIFEST_LIMIT)
        except (TypeError, ValueError):
            limit = _DEFAULT_MANIFEST_LIMIT
        files = build_manifest(school, entities=entities, limit=limit)
        return Response(
            {
                "ok": True,
                "count": len(files),
                # The box needs to know whether it saw everything, or whether the cap cut
                # the list short — otherwise a large school looks fully synced forever.
                "truncated": len(files) >= limit,
                "files": files,
            }
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Offline Sync"],
        summary="Download one byte range of a file (resumable)",
        responses={200: bytes, 403: dict, 404: dict},
    ),
    post=extend_schema(
        tags=["Offline Sync"],
        summary="Upload one byte range of a file (resumable, hash-verified)",
        responses={200: dict, 400: dict, 403: dict},
    ),
)
class SyncFileChunkView(_EdgeFileView):
    # A chunk body is raw bytes, not JSON or a form. Without this DRF's default parsers
    # reject it as unsupported media before post() is ever entered.
    parser_classes: list = []

    def get(self, request):
        school, refusal = self._school(request)
        if refusal is not None:
            return refusal
        path = (request.query_params.get("path") or "").strip()
        if not path or path not in servable_paths(school):
            # Deliberately the same answer for "not yours" and "does not exist": telling
            # the caller which of the two it was is a probe for other tenants' filenames.
            return Response({"ok": False, "error": "unknown_path"}, status=404)
        try:
            offset = max(0, int(request.query_params.get("offset") or 0))
            length = min(
                max(1, int(request.query_params.get("length") or _DEFAULT_CHUNK_BYTES)),
                _MAX_CHUNK_BYTES,
            )
        except (TypeError, ValueError):
            return Response({"ok": False, "error": "invalid_range"}, status=400)

        size, digest = file_stat(path)
        try:
            with default_storage.open(path, "rb") as fh:
                fh.seek(offset)
                data = fh.read(length)
        except Exception:  # noqa: BLE001 - storage error is a 404 to the caller
            return Response({"ok": False, "error": "unreadable"}, status=404)
        resp = HttpResponse(data, content_type="application/octet-stream")
        resp[FILE_SIZE_HEADER] = str(size)
        resp[FILE_SHA256_HEADER] = digest
        resp[FILE_OFFSET_HEADER] = str(offset)
        resp[FILE_COMPLETE_HEADER] = "1" if (offset + len(data)) >= size else "0"
        return resp

    def post(self, request):
        school, refusal = self._school(request)
        if refusal is not None:
            return refusal
        path = (request.headers.get(FILE_PATH_HEADER) or "").strip()
        if not path or path not in servable_paths(school):
            # The ROW must already be on the cloud for its path to be servable. That is
            # the right coupling: files follow data, so a file whose record has not synced
            # yet is refused now and accepted on a later pass, rather than landing as an
            # orphan nothing references.
            return Response({"ok": False, "error": "unknown_path"}, status=404)
        try:
            offset = max(0, int(request.headers.get(FILE_OFFSET_HEADER) or 0))
            declared_size = max(0, int(request.headers.get(FILE_SIZE_HEADER) or 0))
        except (TypeError, ValueError):
            return Response({"ok": False, "error": "invalid_range"}, status=400)
        declared_sha = (request.headers.get(FILE_SHA256_HEADER) or "").strip().lower()
        body = request.body or b""
        if len(body) > _MAX_CHUNK_BYTES:
            return Response(
                {"ok": False, "error": "chunk_too_large", "max_bytes": _MAX_CHUNK_BYTES},
                status=400,
            )
        ceiling = max_file_bytes()
        if ceiling and declared_size > ceiling:
            return Response(
                {"ok": False, "error": "file_too_large", "max_bytes": ceiling}, status=400
            )

        staged = staging_path(getattr(school, "pk", ""), path)
        have = os.path.getsize(staged) if os.path.exists(staged) else 0
        if offset != have:
            # Tell the sender where we actually are instead of silently writing a hole.
            # A hole would hash wrong at the end and the whole transfer would restart,
            # which on a bad link is the difference between converging and not.
            return Response(
                {"ok": False, "error": "offset_mismatch", "expected_offset": have}, status=409
            )
        with open(staged, "ab") as fh:
            fh.write(body)
        received = os.path.getsize(staged)
        if declared_size and received < declared_size:
            return Response({"ok": True, "complete": False, "bytes_received": received})

        # Complete: verify BEFORE committing. A truncated or corrupted transfer that got
        # written into storage would be indistinguishable from a good one afterwards.
        digest = hashlib.sha256()
        with open(staged, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
        actual = digest.hexdigest()
        if declared_sha and actual != declared_sha:
            os.remove(staged)
            return Response(
                {"ok": False, "error": "hash_mismatch", "expected": declared_sha, "actual": actual},
                status=400,
            )
        with open(staged, "rb") as fh:
            payload = fh.read()
        if default_storage.exists(path):
            default_storage.delete(path)
        default_storage.save(path, ContentFile(payload))
        os.remove(staged)
        return Response(
            {"ok": True, "complete": True, "bytes_received": received, "sha256": actual}
        )


__all__ = [
    "FILE_COMPLETE_HEADER",
    "FILE_OFFSET_HEADER",
    "FILE_PATH_HEADER",
    "FILE_SHA256_HEADER",
    "FILE_SIZE_HEADER",
    "SyncFileChunkView",
    "SyncFileManifestView",
    "file_sync_enabled",
    "staging_path",
]
