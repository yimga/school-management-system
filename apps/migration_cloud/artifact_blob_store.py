"""Phase U5 — per-artifact content store (gap #2).

The one place that captures, reads, purges, and drops the encrypted-at-rest
copy of each artifact's source bytes. Everything crypto- / settings- / lifecycle-
related lives here so the wiring in ``services.py`` (capture), ``profiler.py`` +
``orchestrator.py`` (read), ``reconciliation.py`` (drop-on-reconcile), and
``platform_runtime/periodic.py`` (daily purge) stay one-liners.

Why it exists
-------------
``BundleIngestionService.ingest`` creates each ``MigrationArtifact`` with
metadata only and drops ``ArtifactPayload.content_opener`` — a lazy stream
callable that cannot survive the ingest → profile process boundary. So the
profiler and orchestrator could only read bytes for the *single top-level local
file* at ``bundle.intake_source_uri``; **archive members and remote / OAuth-folder
pulls** profiled schema-only and applied zero rows silently. Capturing the bytes
at ingest — while the opener is still valid — and reading them back here closes
that gap.

Security posture
----------------
The bytes are student PII. They are Fernet-encrypted at rest (shared shim /
key / rotation), retention-bounded (``expires_at`` + daily purge + drop on
RECONCILED), size-bounded (inline cap), tenant-isolated (reachable only via
``artifact → bundle → school``), and NEVER logged.
"""

from __future__ import annotations

import hashlib
import io
import logging
from datetime import timedelta
from typing import IO, Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import MigrationArtifactBlob

logger = logging.getLogger(__name__)

# Defaults mirror the approved gap #2 design (7-day retention / delete-on-reconcile
# ON / inline cap). All four are env / settings overridable.
# The cap was raised 10 MB -> 64 MB (2026-07-24 audit BLOCKER 1): a real district
# roster CSV is 10-50 MB, and at 10 MB every such file (and every companion vendor
# export / remote pull > 10 MB) was silently skipped, leaving apply to yield zero
# rows with no error. 64 MB covers whole-school single-file exports; anything still
# over cap is now QUARANTINED (visible), never silently dropped.
_DEFAULT_MAX_INLINE_BYTES = 64 * 1024 * 1024  # magic-number-allow: 64 MB inline blob cap (bytes)
_DEFAULT_RETENTION_DAYS = 7  # magic-number-allow: source-PII retention window (days)


def blob_store_enabled() -> bool:
    """Whether NEW captures happen at ingest. Reads of existing blobs are unconditional."""
    return bool(getattr(settings, "MIGRATION_CLOUD_ARTIFACT_BLOB_STORE_ENABLED", True))


def max_inline_bytes() -> int:
    try:
        return max(0, int(getattr(settings, "MIGRATION_CLOUD_ARTIFACT_BLOB_MAX_INLINE_BYTES", _DEFAULT_MAX_INLINE_BYTES)))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_INLINE_BYTES


def retention_days() -> int:
    try:
        return max(1, int(getattr(settings, "MIGRATION_CLOUD_ARTIFACT_BLOB_RETENTION_DAYS", _DEFAULT_RETENTION_DAYS)))
    except (TypeError, ValueError):
        return _DEFAULT_RETENTION_DAYS


def delete_on_reconcile_enabled() -> bool:
    return bool(getattr(settings, "MIGRATION_CLOUD_ARTIFACT_BLOB_DELETE_ON_RECONCILE", True))


def _safe_close(stream: Any) -> None:
    try:
        stream.close()
    except Exception:  # noqa: BLE001 — best-effort close
        pass


def capture_artifact_blob(artifact: Any, payload: Any) -> bool:
    """Best-effort: store ``artifact``'s source bytes encrypted-at-rest. Never raises.

    Called right after the artifact row is created at ingest, where
    ``payload.content_opener`` is still a live callable. Returns True when a blob
    was written, False when skipped (flag off, no opener, empty, over the size
    cap, or any error — capture must never block ingest).
    """
    if not blob_store_enabled():
        return False
    opener = getattr(payload, "content_opener", None)
    if opener is None:
        return False
    try:
        cap = max_inline_bytes()
        stream = opener()
        try:
            data = stream.read(cap + 1)
        finally:
            _safe_close(stream)
        if not data:
            return False
        if isinstance(data, str):
            data = data.encode(getattr(artifact, "encoding", "") or "utf-8", errors="replace")
        data = bytes(data)
        if len(data) > cap:
            # Over the inline cap: DO NOT silently skip. A silent skip leaves the
            # artifact with no blob and — for archive members / companion exports /
            # remote pulls — no fallback byte source, so apply yields zero rows with
            # NO error: silent data loss at exactly district scale. Mark the artifact
            # quarantined with a visible reason so the operator sees the file was too
            # large to migrate rather than a false green.
            # See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (BLOCKER 1).
            true_size = getattr(artifact, "byte_size", None) or f">{cap}"
            try:
                artifact.quarantined = True
                artifact.quarantine_reason = (
                    f"Source file ({true_size} bytes) exceeds the {cap}-byte inline "
                    "migration cap; not applied. Split the file or raise "
                    "MIGRATION_CLOUD_ARTIFACT_BLOB_MAX_INLINE_BYTES."
                )
                artifact.save(update_fields=["quarantined", "quarantine_reason", "updated_at"])
            except Exception:  # noqa: BLE001 — quarantine mark is best-effort, never blocks ingest
                logger.warning(
                    "migration_cloud.artifact_blob: over-cap quarantine mark failed",
                    extra={"artifact_id": getattr(artifact, "pk", None)},
                    exc_info=True,
                )
            # No PII in the log — id + cap only.
            logger.info(
                "migration_cloud.artifact_blob: artifact over inline cap; quarantined",
                extra={"artifact_id": getattr(artifact, "pk", None), "cap_bytes": cap},
            )
            return False
        digest = hashlib.sha256(data).hexdigest()
        expires = timezone.now() + timedelta(days=retention_days())
        with transaction.atomic():
            # tenant-isolation-allow: blob-scoped-via-artifact-fk-created-at-ingest-under-bundle
            MigrationArtifactBlob.objects.update_or_create(
                artifact=artifact,
                defaults={
                    "payload": data,
                    "byte_size": len(data),
                    "sha256": digest,
                    "expires_at": expires,
                },
            )
        return True
    except Exception:  # noqa: BLE001 — capture never blocks ingest
        logger.warning(
            "migration_cloud.artifact_blob: capture failed",
            extra={"artifact_id": getattr(artifact, "pk", None)},
            exc_info=True,
        )
        return False


def open_artifact_blob_stream(artifact: Any) -> tuple[IO[bytes] | None, str]:
    """Return ``(BytesIO, encoding)`` for the artifact's stored bytes, or ``(None, "")``.

    Reads are unconditional (not gated on the enable flag) so a blob captured
    before the flag was toggled off still resolves until it is purged. The
    plaintext sha256 is re-verified on every read; a mismatch is ignored (falls
    back to the caller's own path logic) rather than trusted.
    """
    # tenant-isolation-allow: blob-lookup-by-artifact-pk-reachable-only-via-bundle-school
    blob = MigrationArtifactBlob.objects.filter(artifact_id=getattr(artifact, "pk", None)).first()
    if blob is None:
        return None, ""
    try:
        data = bytes(blob.payload or b"")
    except (TypeError, ValueError):
        return None, ""
    if not data:
        return None, ""
    if blob.sha256 and hashlib.sha256(data).hexdigest() != blob.sha256:
        logger.warning(
            "migration_cloud.artifact_blob: sha256 mismatch on read; ignoring blob",
            extra={"artifact_id": getattr(artifact, "pk", None)},
        )
        return None, ""
    return io.BytesIO(data), (getattr(artifact, "encoding", "") or "utf-8")


def purge_expired_artifact_blobs() -> dict[str, int]:
    """Delete every blob past ``expires_at``. The daily PII-minimisation sweep."""
    now = timezone.now()
    # tenant-isolation-allow: platform-shared-public-schema-blob-purge-by-expiry-no-tenant-fk
    qs = MigrationArtifactBlob.objects.filter(expires_at__lt=now)
    deleted, _detail = qs.delete()
    if deleted:
        logger.info(
            "migration_cloud.artifact_blob: purged expired source blobs",
            extra={"deleted": int(deleted)},
        )
    return {"deleted": int(deleted)}


def delete_blobs_for_bundle(bundle: Any) -> int:
    """Drop all source blobs for a bundle (called when it reaches RECONCILED).

    No-op when delete-on-reconcile is disabled. Artifact metadata is untouched —
    only the raw bytes go.
    """
    if not delete_on_reconcile_enabled():
        return 0
    # tenant-isolation-allow: bundle-scoped-cascade-via-artifact-fk-drop-source-bytes-on-reconcile
    qs = MigrationArtifactBlob.objects.filter(artifact__bundle_id=getattr(bundle, "pk", None))
    deleted, _detail = qs.delete()
    if deleted:
        logger.info(
            "migration_cloud.artifact_blob: dropped source blobs on reconcile",
            extra={"bundle_id": getattr(bundle, "pk", None), "deleted": int(deleted)},
        )
    return int(deleted)
