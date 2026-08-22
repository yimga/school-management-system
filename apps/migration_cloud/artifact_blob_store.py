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


def _mark_artifact_uncaptured_if_expected(artifact: Any, *, reason: str) -> None:
    """Quarantine an artifact that SHOULD have carried bytes but captured none.

    A silent skip leaves the artifact with no blob and no fallback byte source, so
    apply yields zero rows for it — and a MIXED bundle (some artifacts captured,
    some not) is NOT caught by the orchestrator's all-quarantined honesty gate, so
    the bundle goes green APPLIED with those files contributing nothing (silent
    PARTIAL data loss). When the artifact reported a non-zero ``byte_size`` the
    empty capture is an anomaly (a broken adapter opener, a truncated read, or a
    metadata-only row) — quarantine it with a visible reason so the operator review
    surface + the all-quarantined gate see it. A genuinely empty (0-byte) artifact
    stays silent (nothing to capture is correct). Best-effort: never raises.
    """
    try:
        if int(getattr(artifact, "byte_size", 0) or 0) <= 0:
            return
        if getattr(artifact, "quarantined", False):
            return
        artifact.quarantined = True
        artifact.quarantine_reason = (
            f"Source bytes could not be captured for migration ({reason}); not "
            "applied. Re-upload the file or re-run the source connection."
        )
        artifact.save(update_fields=["quarantined", "quarantine_reason", "updated_at"])
        logger.warning(
            "migration_cloud.artifact_blob: artifact reported bytes but none captured; quarantined",
            extra={"artifact_id": getattr(artifact, "pk", None), "reason": reason},
        )
    except Exception:  # noqa: BLE001 — quarantine mark is best-effort, never blocks ingest
        logger.warning(
            "migration_cloud.artifact_blob: uncaptured-artifact quarantine mark failed",
            extra={"artifact_id": getattr(artifact, "pk", None)},
            exc_info=True,
        )


_av_unconfigured_warned = False


def _warn_artifact_av_unconfigured() -> None:
    """One-time WARNING that ingest artifacts are not malware-scanned (no scanner)."""
    global _av_unconfigured_warned
    if not _av_unconfigured_warned:
        _av_unconfigured_warned = True
        logger.warning(
            "migration_cloud.artifact_blob: no UPLOAD_MALWARE_SCANNER configured — "
            "ingest artifacts are size/quarantine-gated but NOT malware-scanned. "
            "Set UPLOAD_MALWARE_SCANNER to enable.",
        )


def _artifact_bytes_av_clean(artifact: Any, data: bytes) -> bool:
    """Malware-scan the captured (soon-to-be-applied) artifact bytes.

    Extends the self-serve upload AV gate
    (``services/intake_pipeline._validate_export_upload``) to EVERY intake method:
    this chokepoint captures the bytes that will actually be applied, for operator
    FILE_UPLOAD, URL/SFTP/S3, API_PULL, EMAIL, DATABASE, ACCESS_DB and PDF alike.
    Pluggable via ``settings.UPLOAD_MALWARE_SCANNER``; unset -> a one-time-logged
    no-op (never a silent clean). Only a DETECTION quarantines the artifact; a
    scanner ERROR or absence fails open so a misconfigured scanner can't wedge
    every ingest. Returns True when the bytes may be stored/applied.
    """
    from django.conf import settings

    if getattr(settings, "UPLOAD_MALWARE_SCANNER", None) is None:
        _warn_artifact_av_unconfigured()
        return True
    try:
        from apps.security.upload_validation import scan_for_malware

        ok, detail = scan_for_malware(data)
    except Exception:  # noqa: BLE001 — a scanner error must never wedge ingest
        logger.warning(
            "migration_cloud.artifact_blob: AV scan errored; not blocking",
            extra={"artifact_id": getattr(artifact, "pk", None)},
            exc_info=True,
        )
        return True
    if ok:
        return True
    try:
        artifact.quarantined = True
        artifact.quarantine_reason = f"Blocked by malware scan: {detail}"[:255]
        artifact.save(update_fields=["quarantined", "quarantine_reason", "updated_at"])
    except Exception:  # noqa: BLE001 — quarantine mark is best-effort, never blocks ingest
        logger.warning(
            "migration_cloud.artifact_blob: AV quarantine mark failed",
            extra={"artifact_id": getattr(artifact, "pk", None)},
            exc_info=True,
        )
    logger.warning(
        "migration_cloud.artifact_blob: artifact blocked by malware scan; quarantined",
        extra={"artifact_id": getattr(artifact, "pk", None)},
    )
    return False


def capture_artifact_blob(artifact: Any, payload: Any) -> bool:
    """Best-effort: store ``artifact``'s source bytes encrypted-at-rest. Never raises.

    Called right after the artifact row is created at ingest, where
    ``payload.content_opener`` is still a live callable. Returns True when a blob
    was written, False when skipped (flag off, no opener, empty, over the size
    cap, or any error — capture must never block ingest). An artifact that
    reported bytes (``byte_size > 0``) but captured none is quarantined visibly so
    the failure is never silent (see ``_mark_artifact_uncaptured_if_expected``).
    """
    if not blob_store_enabled():
        return False
    opener = getattr(payload, "content_opener", None)
    if opener is None:
        _mark_artifact_uncaptured_if_expected(artifact, reason="no content stream")
        return False
    try:
        cap = max_inline_bytes()
        stream = opener()
        try:
            data = stream.read(cap + 1)
        finally:
            _safe_close(stream)
        if not data:
            _mark_artifact_uncaptured_if_expected(artifact, reason="empty source read")
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
        # Malware-scan the bytes that will actually be stored + applied. A hit
        # quarantines the artifact and skips the blob (never store/apply malware);
        # unset scanner -> logged no-op. Extends AV coverage to every intake method.
        if not _artifact_bytes_av_clean(artifact, data):
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


def clone_artifact_blob(src_artifact: Any, dst_artifact: Any) -> bool:
    """Copy ``src_artifact``'s stored bytes onto a NEW ``dst_artifact`` row.

    ``MigrationArtifactBlob`` is a OneToOne keyed to the artifact PK, so when a
    flow creates a *new* artifact row (sandbox clone, multi-bundle merge) the new
    PK has no blob — and, because merge rewrites ``path_within_bundle``, it cannot
    even fall back to the single-top-level-local-file path. Without this copy the
    downstream apply of a blob-backed artifact (archive member / companion /
    remote / bulk-API upload) resolves to zero rows silently. Best-effort: never
    raises. Returns True when a blob was copied, False when the source had none.
    """
    src_pk = getattr(src_artifact, "pk", None)
    dst_pk = getattr(dst_artifact, "pk", None)
    if not src_pk or not dst_pk:
        return False
    # tenant-isolation-allow: blob-lookup-by-artifact-pk-reachable-only-via-bundle-school
    src = MigrationArtifactBlob.objects.filter(artifact_id=src_pk).first()
    if src is None:
        return False
    try:
        data = bytes(src.payload or b"")
        if not data:
            return False
        with transaction.atomic():
            # tenant-isolation-allow: blob-clone-scoped-via-dst-artifact-fk-created-under-bundle
            MigrationArtifactBlob.objects.update_or_create(
                artifact=dst_artifact,
                defaults={
                    "payload": data,
                    "byte_size": src.byte_size or len(data),
                    "sha256": src.sha256 or hashlib.sha256(data).hexdigest(),
                    "expires_at": src.expires_at
                    or (timezone.now() + timedelta(days=retention_days())),
                },
            )
        return True
    except Exception:  # noqa: BLE001 — blob clone never blocks the clone/merge
        logger.warning(
            "migration_cloud.artifact_blob: clone failed",
            extra={"src_artifact_id": src_pk, "dst_artifact_id": dst_pk},
            exc_info=True,
        )
        return False


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
    return purge_source_blobs_for_bundle(bundle, respect_setting=True)


def source_blob_count(bundle: Any) -> int:
    """Count captured source blobs still stored for a bundle."""
    bundle_id = getattr(bundle, "pk", None)
    if not bundle_id:
        return 0
    try:
        from .models import MigrationArtifactBlob

        return MigrationArtifactBlob.objects.filter(artifact__bundle_id=bundle_id).count()
    except Exception:  # noqa: BLE001
        logger.debug("artifact_blob: source_blob_count failed", exc_info=True)
        return 0


def bundle_source_archived(bundle: Any) -> bool:
    """True when source bytes were dropped (auto on reconcile or manual archive)."""
    summary = getattr(bundle, "size_summary", None) or {}
    if summary.get("source_archived_at"):
        return True
    return source_blob_count(bundle) == 0 and bool(summary.get("reconciled_at"))


def purge_source_blobs_for_bundle(bundle: Any, *, respect_setting: bool = True) -> int:
    """Delete encrypted source blobs for every artifact on the bundle."""
    if respect_setting and not delete_on_reconcile_enabled():
        return 0
    bundle_id = getattr(bundle, "pk", None)
    if not bundle_id:
        return 0
    try:
        from .models import MigrationArtifactBlob
    except Exception:  # noqa: BLE001
        return 0
    # tenant-isolation-allow: bundle-scoped-cascade-via-artifact-fk-drop-source-bytes-on-reconcile
    qs = MigrationArtifactBlob.objects.filter(artifact__bundle_id=bundle_id)
    deleted, _detail = qs.delete()
    if deleted:
        logger.info(
            "migration_cloud.artifact_blob: dropped source blobs",
            extra={"bundle_id": bundle_id, "deleted": int(deleted)},
        )
    return int(deleted)


def archive_bundle_source_files(bundle: Any, *, actor_id: int | None = None) -> dict[str, Any]:
    """Operator/tenant manual archive — drop source bytes and stamp metadata."""
    from django.utils import timezone as tz

    summary = dict(getattr(bundle, "size_summary", None) or {})
    if summary.get("source_archived_at") and source_blob_count(bundle) == 0:
        return {"ok": True, "deleted": 0, "already_archived": True}

    deleted = purge_source_blobs_for_bundle(bundle, respect_setting=False)
    summary["source_archived_at"] = tz.now().isoformat()
    if actor_id is not None:
        summary["source_archived_by"] = actor_id
    summary["source_blobs_deleted"] = int(deleted)
    bundle.size_summary = summary
    bundle.save(update_fields=["size_summary", "updated_at"])
    return {"ok": True, "deleted": int(deleted), "already_archived": False}
