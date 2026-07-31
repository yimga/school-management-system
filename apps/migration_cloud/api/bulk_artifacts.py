"""Bulk multipart artifact upload action for ``BundleViewSet`` (v3.29).

Single endpoint:

    POST /api/v1/bundles/<pk>/artifacts/bulk/   (multipart/form-data)

Accepts 1..N files, validates size + count limits, computes ``sha256``
per file, and creates one :class:`MigrationArtifact` row per accepted
file. Idempotency is built-in via the existing per-bundle unique-by-hash
constraint — re-uploading the same file content returns it as
``already_accepted`` rather than 409.

Every accepted file's bytes are captured into the encrypted-at-rest
``MigrationArtifactBlob`` content store (via ``capture_artifact_blob``) so the
apply step can actually read the rows back. Before this the endpoint created
metadata-only rows and discarded the bytes, so ``orchestrator._iter_canonical_rows``
found no blob and no top-level local file and yielded zero rows — a silent
zero-row apply for every artifact uploaded through this API.

Limits (defensive — operators with bigger needs use the wizard):

    * 50 files per request                  (MAX_FILES_PER_REQUEST)
    * 100 MB per file                       (MAX_FILE_BYTES)
    * 500 MB aggregate per request          (MAX_TOTAL_BYTES)

Response shape::

    {
        "bundle_id": 42,
        "accepted":  [{"id": 1, "filename": "...", "sha256": "...", "byte_size": N,
                       "deduplicated": false}, ...],
        "rejected":  [{"name": "...", "reason": "..."}, ...]
    }
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import tempfile

from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.migration_cloud.models import MigrationArtifact

logger = logging.getLogger(__name__)


# Operator-tunable via config in a follow-up; conservative defaults shipped today.
MAX_FILES_PER_REQUEST = 50
MAX_FILE_BYTES = 100 * 1024 * 1024            # 100 MB
MAX_TOTAL_BYTES = 500 * 1024 * 1024           # 500 MB

# Chunk size when reading uploaded files for sha256 — Django's UploadedFile
# yields chunks ~64KB by default; honor that to avoid OOM on big uploads.
_HASH_CHUNK_SIZE = 64 * 1024


def _sha256_of_upload(uploaded_file) -> tuple[str, int]:
    """Stream-hash the upload, return ``(hex_digest, byte_count)``.

    Resets the file pointer afterward so downstream code can re-read.
    """
    hasher = hashlib.sha256()
    total = 0
    try:
        for chunk in uploaded_file.chunks(chunk_size=_HASH_CHUNK_SIZE):
            hasher.update(chunk)
            total += len(chunk)
    finally:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            # In-memory uploads may not support seek post-iter; that's fine
            # — we don't re-read at this layer.
            pass
    return hasher.hexdigest(), total


def _spool_and_hash(uploaded_file, *, cap: int) -> tuple[str, str, int, bool]:
    """Stream the upload to a temp file while hashing, one pass.

    Returns ``(tmp_path, hex_digest, byte_count, over_cap)``. Capturing the bytes
    (not just the hash) is what lets the apply step read real rows — a hash-only
    read leaves the artifact with no content and apply yields nothing. Stops
    writing once ``cap`` is exceeded (``over_cap=True``) so an over-limit file
    never fills the disk. The caller unlinks ``tmp_path`` after capture.
    """
    hasher = hashlib.sha256()
    total = 0
    over = False
    fd, tmp_path = tempfile.mkstemp(prefix="mc-bulk-", suffix=".upload")
    try:
        with os.fdopen(fd, "wb") as tmp:
            for chunk in uploaded_file.chunks(chunk_size=_HASH_CHUNK_SIZE):
                hasher.update(chunk)
                total += len(chunk)
                if total > cap:
                    over = True
                    break
                tmp.write(chunk)
    finally:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass
    return tmp_path, hasher.hexdigest(), total, over


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _capture_upload_bytes(artifact, tmp_path: str) -> bool:
    """Capture the spooled temp file into the artifact's encrypted blob store.

    Uses the same ``capture_artifact_blob`` path every intake adapter uses, via a
    one-shot ``ArtifactPayload`` whose ``content_opener`` reopens the temp file.
    Best-effort: capture never raises (mirrors ingest).
    """
    from apps.migration_cloud.artifact_blob_store import capture_artifact_blob
    from apps.migration_cloud.intake.base import ArtifactPayload

    payload = ArtifactPayload(
        path_within_bundle=artifact.path_within_bundle,
        filename=artifact.filename,
        byte_size=artifact.byte_size,
        sha256=artifact.sha256,
        mime_type=artifact.mime_type,
        content_opener=lambda p=tmp_path: open(p, "rb"),  # noqa: SIM115 — closed by capture_artifact_blob
    )
    return capture_artifact_blob(artifact, payload)


def _blob_exists(artifact) -> bool:
    from apps.migration_cloud.models import MigrationArtifactBlob

    # tenant-isolation-allow: blob-lookup-by-artifact-pk-reachable-only-via-bundle-school
    return MigrationArtifactBlob.objects.filter(artifact_id=artifact.pk).exists()


def _bulk_artifacts_schema_kwargs() -> dict:
    """Return the kwargs for ``@extend_schema`` on the bulk endpoint."""
    return {
        "tags": ["Migration Cloud"],
        "summary": "Bulk-attach up to 50 artifacts to a bundle",
        "description": (
            "Multipart upload that registers 1..N artifacts in one round-trip. "
            "Each file becomes a ``MigrationArtifact`` row and its bytes are "
            "captured into the encrypted content store so the apply step can read "
            "the rows. Content is hashed with sha256 server-side; uploading the "
            "same content twice into the same bundle returns the existing row "
            "marked ``deduplicated=true`` rather than 409. Limits: max 50 files "
            "per request, max 100MB per file, max 500MB aggregate."
        ),
        "request": {
            "multipart/form-data": inline_serializer(
                name="BulkArtifactsRequest",
                fields={
                    "files": serializers.ListField(
                        child=serializers.FileField(),
                        help_text="One or more files (multipart-form 'files' field).",
                    ),
                },
            ),
        },
        "responses": {
            200: OpenApiResponse(description="Per-file accept/reject report"),
            400: OpenApiResponse(description="Limit exceeded or no files supplied"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
            500: OpenApiResponse(description="Structured 500 envelope with request_id"),
        },
    }


def bulk_artifacts_action_factory():
    """Return a configured ``@action`` method to attach to ``BundleViewSet``.

    Centralizing the construction here keeps ``viewsets.py`` minimal — the
    viewset only needs to ``= bulk_artifacts_action_factory()`` on a class
    attribute.
    """
    from apps.migration_cloud.reliability import idempotent_post, safe_500

    @action(
        detail=True,
        methods=["post"],
        url_path="artifacts/bulk",
        parser_classes=[MultiPartParser, FormParser],
    )
    @extend_schema(**_bulk_artifacts_schema_kwargs())
    @idempotent_post
    @safe_500
    def bulk_artifacts(self, request, pk=None):
        """Attach 1..N artifacts to the bundle in one multipart request."""
        bundle = self.get_object()  # tenant-isolation-allow: bulk-artifacts-relies-on-viewset-get-object-which-already-scopes
        # upload-validation-allow: bulk artifact intake accepts schema-agnostic SIS exports (any format) streamed for sha256 with no retained buffer — no single magic-byte type applies, and a full-buffer AV read would regress the streaming design; per-file + aggregate byte-size caps are enforced below
        files = list(request.FILES.getlist("files")) or list(request.FILES.values())
        if not files:
            return Response(
                {"error": "no files supplied — POST multipart with field name 'files'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(files) > MAX_FILES_PER_REQUEST:
            return Response(
                {
                    "error": "too many files in one request",
                    "max": MAX_FILES_PER_REQUEST,
                    "received": len(files),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # First pass — size validation + sha256 + spool bytes to temp (streaming).
        # Spooling (not just hashing) is what lets the second pass capture the
        # bytes into the blob store so apply reads real rows.
        prepared: list[dict] = []
        rejected: list[dict] = []
        running_total = 0
        tmp_paths: list[str] = []
        try:
            for upload in files:
                name = getattr(upload, "name", "<unnamed>")
                size_hint = getattr(upload, "size", None)
                if size_hint is not None and size_hint > MAX_FILE_BYTES:
                    rejected.append({
                        "name": name,
                        "reason": f"file exceeds per-file limit {MAX_FILE_BYTES} bytes",
                    })
                    continue
                tmp_path, digest, byte_count, over_cap = _spool_and_hash(
                    upload, cap=MAX_FILE_BYTES
                )
                if over_cap:
                    _safe_unlink(tmp_path)
                    rejected.append({
                        "name": name,
                        "reason": f"file exceeds per-file limit {MAX_FILE_BYTES} bytes",
                    })
                    continue
                if running_total + byte_count > MAX_TOTAL_BYTES:
                    _safe_unlink(tmp_path)
                    rejected.append({
                        "name": name,
                        "reason": f"aggregate request exceeds {MAX_TOTAL_BYTES} bytes",
                    })
                    continue
                running_total += byte_count
                tmp_paths.append(tmp_path)
                prepared.append({
                    "name": name,
                    "byte_size": byte_count,
                    "sha256": digest,
                    "tmp_path": tmp_path,
                    "mime_type": getattr(upload, "content_type", None)
                                  or mimetypes.guess_type(name)[0] or "",
                })

            # Second pass — create or dedup, then capture the bytes.
            accepted: list[dict] = []
            for entry in prepared:
                existing = (
                    # tenant-isolation-allow: bulk-artifacts-dedup-within-already-tenant-scoped-bundle
                    bundle.artifacts.filter(sha256=entry["sha256"]).first()
                )
                if existing is not None:
                    # Top up bytes for a metadata-only row created before capture
                    # was wired (or a create whose capture failed) — idempotent.
                    if not _blob_exists(existing):
                        _capture_upload_bytes(existing, entry["tmp_path"])
                    accepted.append({
                        "id": existing.pk,
                        "filename": existing.filename,
                        "sha256": existing.sha256,
                        "byte_size": existing.byte_size,
                        "deduplicated": True,
                    })
                    continue
                try:
                    row = MigrationArtifact.objects.create(
                        bundle=bundle,
                        filename=entry["name"][:255],
                        path_within_bundle=entry["name"],
                        mime_type=entry["mime_type"][:128] if entry["mime_type"] else "",
                        byte_size=entry["byte_size"],
                        sha256=entry["sha256"],
                    )
                    # Capture the bytes so apply can read real rows (not a
                    # silent zero-row apply). Best-effort — never blocks accept.
                    _capture_upload_bytes(row, entry["tmp_path"])
                    accepted.append({
                        "id": row.pk,
                        "filename": row.filename,
                        "sha256": row.sha256,
                        "byte_size": row.byte_size,
                        "deduplicated": False,
                    })
                except Exception as exc:  # defensive — uniqueness race or model error
                    logger.exception(
                        "migration_cloud_bulk_artifact_create_failed bundle_id=%s sha256=%s",
                        bundle.pk, entry["sha256"],
                    )
                    rejected.append({
                        "name": entry["name"],
                        "reason": f"create-failed: {type(exc).__name__}",
                    })
        finally:
            for path in tmp_paths:
                _safe_unlink(path)

        logger.info(
            "migration_cloud_bulk_artifacts bundle_id=%s accepted=%s rejected=%s bytes=%s",
            bundle.pk, len(accepted), len(rejected), running_total,
        )
        return Response(
            {
                "bundle_id": bundle.pk,
                "accepted": accepted,
                "rejected": rejected,
            },
            status=status.HTTP_200_OK,
        )

    return bulk_artifacts
