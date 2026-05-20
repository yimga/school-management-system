"""Safe import engine — bridges connector workflow to MigrationBundle + orchestrator."""

from __future__ import annotations

import logging
import secrets
from decimal import Decimal

from django.db import transaction
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


@transaction.atomic
def run_connector_import(
    *,
    connection: MigrationSourceConnection,
    staging_batch: MigrationStagingBatch,
    started_by,
    idempotency_key: str | None = None,
    quality_override: bool = False,
    dry_run: bool = False,
    dry_run_apply: bool = False,
) -> MigrationImportRun:
    if connection.status != SourceConnectionStatus.VERIFIED:
        raise ValueError("import_requires_verified_connection")
    if not connection.authorization_confirmed:
        raise ValueError("import_requires_authorization")

    missing = required_fields_blocked(connection, staging_batch.entity_type)
    if missing:
        raise ValueError(f"import_blocked_unmapped_required:{','.join(missing)}")

    if not _quality_threshold_met(staging_batch, override=quality_override):
        raise ValueError("import_blocked_data_quality_threshold")

    key = idempotency_key or f"connector:{connection.id}:{staging_batch.id}"
    existing = MigrationImportRun.objects.filter(
        school=connection.school,
        idempotency_key=key,
    ).first()
    if existing and existing.status in (ImportRunStatus.COMPLETED, ImportRunStatus.RUNNING):
        return existing

    import_run = MigrationImportRun.objects.create(
        school=connection.school,
        source_connection=connection,
        staging_batch=staging_batch,
        status=ImportRunStatus.PREVIEW if dry_run else ImportRunStatus.READY,
        idempotency_key=key,
        started_by=started_by,
    )

    if dry_run:
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
        )
        apply_block = pipeline.get("apply") or {}
        import_run.created_counts = {
            "created": apply_block.get("total_created", 0),
            "artifacts": pipeline.get("advance", {}).get("artifacts_profiled", 0),
        }
        import_run.updated_counts = {"updated": apply_block.get("total_updated", 0)}
        import_run.skipped_counts = {"quarantined": apply_block.get("total_quarantined", 0)}
        import_run.rollback_snapshot_reference = f"bundle:{bundle.pk}:{pipeline.get('bundle_status')}"
        import_run.status = ImportRunStatus.COMPLETED
        import_run.completed_at = timezone.now()
        import_run.audit_summary = {
            "bundle_id": bundle.pk,
            "bundle_status": pipeline.get("bundle_status"),
            "dry_run_apply": dry_run_apply,
            "pipeline": pipeline,
        }
        import_run.save()

        purge_source_credentials(connection)
        record_connector_import(connection.school_id, status="completed")

        record_connector_audit(
            school=connection.school,
            actor=started_by,
            event_type="import_completed",
            source_connection=connection,
            import_run=import_run,
            metadata={"bundle_id": bundle.pk, "bundle_status": pipeline.get("bundle_status")},
        )
    except Exception as exc:  # noqa: BLE001
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

    return import_run


def generate_idempotency_key() -> str:
    return secrets.token_urlsafe(24)
