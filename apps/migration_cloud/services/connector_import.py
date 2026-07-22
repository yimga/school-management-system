"""Safe import engine — bridges connector workflow to MigrationBundle + orchestrator."""

from __future__ import annotations

import logging
import secrets
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.migration_cloud.metrics import record_connector_import
from apps.migration_cloud.models_connectors import (
    ImportRunStatus,
    MigrationImportRun,
    MigrationSourceConnection,
    MigrationStagingBatch,
    SourceConnectionStatus,
)
from apps.migration_cloud.services.connector_audit import record_connector_audit
from apps.migration_cloud.services.connector_bundle_bridge import (
    ingest_staged_csv_to_bundle,
    run_bundle_pipeline,
    write_staging_csv,
)
from apps.migration_cloud.services.connector_credentials import purge_source_credentials
from apps.migration_cloud.services.connector_mapping import required_fields_blocked
logger = logging.getLogger(__name__)

MIN_QUALITY_SCORE = Decimal("70.00")


def _quality_threshold_met(batch: MigrationStagingBatch, *, override: bool) -> bool:
    if override:
        return True
    score = batch.data_quality_score
    if score is None:
        return False
    return score >= MIN_QUALITY_SCORE


def run_connector_import(
    *,
    connection: MigrationSourceConnection,
    staging_batch: MigrationStagingBatch,
    started_by,
    idempotency_key: str | None = None,
    quality_override: bool = False,
    dry_run: bool = False,
    dry_run_apply: bool = False,
    off_http: bool = False,
) -> MigrationImportRun:
    # NB: this function is deliberately NOT wrapped in a single
    # ``@transaction.atomic``. The FAILED-status write + audit trail in the
    # except block MUST survive so a failed import is visible in the DB — under
    # a function-level atomic the trailing ``raise`` unwound the transaction and
    # discarded the FAILED save, the import_started audit, AND the run row
    # itself, leaving no record of the failure. The row-landing work gets its
    # own nested atomic instead; the bookkeeping writes commit independently.
    if connection.status != SourceConnectionStatus.VERIFIED:
        raise ValueError("import_requires_verified_connection")
    if not connection.authorization_confirmed:
        raise ValueError("import_requires_authorization")

    missing = required_fields_blocked(connection, staging_batch.entity_type)
    if missing:
        raise ValueError(f"import_blocked_unmapped_required:{','.join(missing)}")

    # Guard the empty-batch case explicitly: without rows the bundle bridge would
    # write a placeholder and report a "completed" import of zero records (silent
    # no-op). This is NOT overridable by quality_override — an empty import is
    # never what the operator wants.
    if not (staging_batch.staged_rows or []):
        raise ValueError("import_blocked_no_rows")

    if not _quality_threshold_met(staging_batch, override=quality_override):
        raise ValueError("import_blocked_data_quality_threshold")

    key = idempotency_key or f"connector:{connection.id}:{staging_batch.id}"
    import_run = _resolve_or_create_run(
        connection=connection,
        staging_batch=staging_batch,
        started_by=started_by,
        key=key,
        dry_run=dry_run,
    )
    # A terminal/in-flight run for this key short-circuits (real idempotency).
    if import_run.status in (ImportRunStatus.COMPLETED, ImportRunStatus.RUNNING):
        return import_run

    if dry_run:
        import_run.status = ImportRunStatus.PREVIEW
        import_run.save(update_fields=["status"])
        record_connector_audit(
            school=connection.school,
            actor=started_by,
            event_type="import_preview",
            source_connection=connection,
            import_run=import_run,
        )
        return import_run

    import_run.status = ImportRunStatus.RUNNING
    import_run.started_at = timezone.now()
    import_run.save(update_fields=["status", "started_at"])

    record_connector_audit(
        school=connection.school,
        actor=started_by,
        event_type="import_started",
        source_connection=connection,
        import_run=import_run,
    )

    try:
        # Only the tenant-row landing + completion bookkeeping is atomic, so a
        # mid-landing failure rolls back partial writes WITHOUT discarding the
        # FAILED record written in the except (which sits outside this block).
        with transaction.atomic():
            rows = list(staging_batch.staged_rows or [])
            csv_path = write_staging_csv(rows=rows, entity_type=staging_batch.entity_type)
            bundle, _registered = ingest_staged_csv_to_bundle(
                csv_path=csv_path,
                school=connection.school,
                idempotency_key=f"bundle-{key}",
                source_hint=connection.source_platform_type,
                label=f"Connector import {staging_batch.entity_type}",
                triggered_by_id=getattr(started_by, "pk", None),
            )
            import_run.bundle = bundle
            connection.linked_bundle = bundle
            connection.save(update_fields=["linked_bundle", "updated_at"])

            pipeline = run_bundle_pipeline(
                bundle_id=bundle.pk,
                source_hint=connection.source_platform_type,
                use_accelerator=True,
                dry_run_apply=dry_run_apply,
                off_http=off_http,
            )
            apply_block = pipeline.get("apply") or {}
            if pipeline.get("queued"):
                import_run.created_counts = {}
                import_run.updated_counts = {}
                import_run.skipped_counts = {}
                import_run.rollback_snapshot_reference = (
                    f"bundle:{bundle.pk}:queued:{pipeline.get('outbox_id')}"
                )
                # Stay RUNNING until a later observer / refresh sees APPLIED;
                # HTTP must not block on advance+apply.
                import_run.status = ImportRunStatus.RUNNING
                import_run.completed_at = None
                import_run.audit_summary = {
                    "bundle_id": bundle.pk,
                    "bundle_status": pipeline.get("bundle_status"),
                    "dry_run_apply": dry_run_apply,
                    "queued": True,
                    "durable_outbox": True,
                    "outbox_id": pipeline.get("outbox_id"),
                    "pipeline": pipeline,
                }
                import_run.save()
            else:
                import_run.created_counts = {
                    "created": apply_block.get("total_created", 0),
                    "artifacts": pipeline.get("advance", {}).get("artifacts_profiled", 0),
                }
                import_run.updated_counts = {"updated": apply_block.get("total_updated", 0)}
                import_run.skipped_counts = {
                    "quarantined": apply_block.get("total_quarantined", 0)
                }
                import_run.rollback_snapshot_reference = (
                    f"bundle:{bundle.pk}:{pipeline.get('bundle_status')}"
                )
                import_run.status = ImportRunStatus.COMPLETED
                import_run.completed_at = timezone.now()
                import_run.audit_summary = {
                    "bundle_id": bundle.pk,
                    "bundle_status": pipeline.get("bundle_status"),
                    "dry_run_apply": dry_run_apply,
                    "pipeline": pipeline,
                }
                import_run.save()

            if not pipeline.get("queued"):
                purge_source_credentials(connection)
    except Exception as exc:  # noqa: BLE001
        # Outside the atomic block above → these writes COMMIT and persist so the
        # failure is not invisible.
        import_run.status = ImportRunStatus.FAILED
        import_run.error_counts = {"error": 1}
        import_run.completed_at = timezone.now()
        import_run.save()
        record_connector_import(connection.school_id, status="failed")
        record_connector_audit(
            school=connection.school,
            actor=started_by,
            event_type="import_failed",
            source_connection=connection,
            import_run=import_run,
            metadata={"error": str(exc)[:120]},
        )
        raise

    if (import_run.audit_summary or {}).get("queued"):
        record_connector_import(connection.school_id, status="queued")
        record_connector_audit(
            school=connection.school,
            actor=started_by,
            event_type="import_queued",
            source_connection=connection,
            import_run=import_run,
            metadata={
                "bundle_id": import_run.bundle_id,
                "outbox_id": (import_run.audit_summary or {}).get("outbox_id"),
            },
        )
        return import_run

    record_connector_import(connection.school_id, status="completed")
    record_connector_audit(
        school=connection.school,
        actor=started_by,
        event_type="import_completed",
        source_connection=connection,
        import_run=import_run,
        metadata={
            "bundle_id": import_run.bundle_id,
            "bundle_status": (import_run.audit_summary or {}).get("bundle_status"),
        },
    )
    return import_run


def _resolve_or_create_run(*, connection, staging_batch, started_by, key, dry_run):
    """Reuse the existing run for this idempotency key, or create one.

    ``MigrationImportRun.idempotency_key`` is GLOBALLY unique. The old code did a
    bare ``create(idempotency_key=key)`` after a filter that only short-circuited
    on COMPLETED/RUNNING — so a prior PREVIEW (dry-run) or FAILED run with the
    same key fell through to the create and raised an uncaught ``IntegrityError``
    (a 500). Reuse any existing run (promoting a re-run), and treat a create race
    as a reuse.
    """
    existing = MigrationImportRun.objects.filter(
        school=connection.school,
        idempotency_key=key,
    ).first()
    if existing is not None:
        if existing.status in (ImportRunStatus.COMPLETED, ImportRunStatus.RUNNING):
            return existing
        # Promote a prior PREVIEW/FAILED/READY run back to a fresh start.
        existing.status = ImportRunStatus.PREVIEW if dry_run else ImportRunStatus.READY
        existing.staging_batch = staging_batch
        existing.source_connection = connection
        existing.started_by = started_by
        existing.save(update_fields=["status", "staging_batch", "source_connection", "started_by"])
        return existing
    try:
        return MigrationImportRun.objects.create(
            school=connection.school,
            source_connection=connection,
            staging_batch=staging_batch,
            status=ImportRunStatus.PREVIEW if dry_run else ImportRunStatus.READY,
            idempotency_key=key,
            started_by=started_by,
        )
    except IntegrityError:
        # Concurrent create for the same key — fetch and reuse the winner.
        run = MigrationImportRun.objects.filter(
            school=connection.school, idempotency_key=key
        ).first()
        if run is None:
            raise
        return run


def generate_idempotency_key() -> str:
    return secrets.token_urlsafe(24)
