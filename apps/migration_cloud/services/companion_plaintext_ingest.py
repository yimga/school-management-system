"""Companion decrypt → Migration Cloud intake (P0-B).

After ``CompanionDecryptHookView`` opens a SealedBox, plaintext MUST be
registered as ``MigrationArtifact`` row(s) via ``BundleIngestionService``
and advanced toward ``MAPPED``. Leaving the bundle at ``INGESTING`` with
zero artifacts was the Phase 0 P0-B gap (comment claimed persist; code discarded).

Hard contracts:
  * Never log plaintext bytes / paths that embed plaintext content.
  * Reuse the existing bundle via its ``idempotency_key``.
  * Best-effort zeroize of a mutable plaintext buffer after ingest.
"""

from __future__ import annotations

import logging
import secrets
from datetime import date
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def guess_filename_and_method(plaintext: bytes) -> tuple[str, str]:
    """Pick a safe filename + intake method from magic bytes (never from content body)."""
    from apps.migration_cloud.models import IntakeMethod

    if plaintext[:4] == b"PK\x03\x04" or plaintext[:4] == b"PK\x05\x06":
        return "companion_export.zip", IntakeMethod.ARCHIVE
    if plaintext[:5] == b"%PDF-":
        return "companion_export.pdf", IntakeMethod.FILE_UPLOAD
    # UTF-8 BOM or JSON object/array
    head = plaintext.lstrip(b"\xef\xbb\xbf")[:1]
    if head in (b"{", b"["):
        return "companion_export.json", IntakeMethod.FILE_UPLOAD
    # Spreadsheet OOXML is also a zip — already handled. XLS legacy D0 CF
    if plaintext[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "companion_export.xls", IntakeMethod.FILE_UPLOAD
    # Default: tabular text (CSV/TSV) — FileIntakeAdapter profiles columns.
    return "companion_export.csv", IntakeMethod.FILE_UPLOAD


def _stage_plaintext_file(*, bundle_id: int, filename: str, plaintext: bytes) -> Path:
    root = Path(getattr(settings, "MEDIA_ROOT", ".") or ".")
    dest_dir = root / "migration_cloud" / "companion" / date.today().isoformat() / str(bundle_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Collision-safe name; never use operator-supplied path segments.
    safe = Path(filename).name.replace("..", "_") or "companion_export.bin"
    dest = dest_dir / f"{secrets.token_hex(4)}_{safe}"
    dest.write_bytes(plaintext)
    return dest


def _zeroize_mutable(buf: bytearray) -> None:
    for i in range(len(buf)):
        buf[i] = 0


def _enqueue_or_inline_advance(bundle_id: int) -> None:
    try:
        from apps.migration_cloud.celery_tasks import enqueue_advance

        if enqueue_advance(bundle_id, use_accelerator=True) is not None:
            return
    except Exception:  # noqa: BLE001
        logger.warning(
            "mc.companion_ingest: enqueue_advance failed bundle_id=%s; inline",
            bundle_id,
        )
    try:
        from apps.migration_cloud.pipeline import advance_bundle

        advance_bundle(bundle_id=bundle_id, use_accelerator=True)
    except Exception:  # noqa: BLE001
        logger.exception(
            "mc.companion_ingest: inline advance failed bundle_id=%s",
            bundle_id,
        )


def ingest_companion_plaintext(*, bundle, plaintext: bytes) -> dict[str, Any]:
    """Persist decrypted companion bytes into ``bundle`` and kick advance.

    Returns a JSON-safe summary (sizes + counts only — never content).
    Raises on hard ingest failure after marking the bundle FAILED when possible.
    """
    from apps.migration_cloud.models import BundleStatus
    from apps.migration_cloud.schema_binding import ensure_bundle_schema_name
    from apps.migration_cloud.services import BundleIngestionService, BundleSpec

    if not plaintext:
        raise ValueError("empty plaintext")

    # Idempotent re-decrypt: artifacts already registered → just advance.
    existing_arts = bundle.artifacts.count()
    if existing_arts > 0:
        ensure_bundle_schema_name(bundle)
        _enqueue_or_inline_advance(bundle.pk)
        return {
            "artifacts_registered": 0,
            "artifacts_already_present": existing_arts,
            "advanced": True,
            "replay": True,
        }

    ensure_bundle_schema_name(bundle)
    filename, method = guess_filename_and_method(plaintext)

    # Mutable copy so we can zeroize after write (immutable bytes stay briefly).
    mutable = bytearray(plaintext)
    try:
        path = _stage_plaintext_file(
            bundle_id=bundle.pk,
            filename=filename,
            plaintext=bytes(mutable),
        )
    finally:
        _zeroize_mutable(mutable)

    uri = (bundle.intake_source_uri or "").strip()
    if "(decrypted)" not in uri:
        uri = f"{uri} (decrypted)".strip() if uri else f"companion://decrypted/{bundle.pk}"

    bundle.intake_source_uri = uri
    bundle.started_at = bundle.started_at or timezone.now()
    bundle.save(update_fields=["intake_source_uri", "started_at", "updated_at"])

    spec = BundleSpec(
        intake_method=method,
        handle=path,
        school_id=bundle.school_id,
        schema_name=bundle.schema_name or "",
        label=bundle.label or f"Companion decrypt — {bundle.pk}",
        source_hint=bundle.source_hint or "",
        idempotency_key=bundle.idempotency_key,
        intake_source_uri=bundle.intake_source_uri,
        triggered_by_id=getattr(bundle, "triggered_by_id", None),
    )
    try:
        result = BundleIngestionService().ingest(spec)
    except Exception:
        try:
            bundle.refresh_from_db()
            if bundle.status != BundleStatus.FAILED:
                bundle.mark_status(
                    BundleStatus.FAILED,
                    summary_patch={
                        "error": "companion_plaintext_ingest_failed",
                        "stage": "companion_decrypt_ingest",
                    },
                )
        except Exception:  # noqa: BLE001
            pass
        raise

    _enqueue_or_inline_advance(result.bundle_id)
    return {
        "artifacts_registered": result.artifacts_registered,
        "artifacts_skipped_duplicate": result.artifacts_skipped_duplicate,
        "total_bytes": result.total_bytes,
        "status": result.status,
        "advanced": True,
        "replay": False,
    }
