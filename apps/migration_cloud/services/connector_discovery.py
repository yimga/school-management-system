"""Source discovery service — preview only, no tenant import."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.migration_cloud.connectors import get_connector
from apps.migration_cloud.models_connectors import (
    DiscoveryRunStatus,
    MigrationDiscoveryRun,
    MigrationSourceConnection,
    SourceConnectionStatus,
)
from apps.migration_cloud.services.connector_audit import record_connector_audit
from apps.migration_cloud.services.connector_credentials import (
    retrieve_source_credential_for_runtime,
)
from apps.platform_runtime import migration_center

logger = logging.getLogger(__name__)


def run_source_discovery(
    *,
    connection: MigrationSourceConnection,
    started_by,
) -> MigrationDiscoveryRun:
    if connection.status != SourceConnectionStatus.VERIFIED:
        raise ValueError("discovery_requires_verified_connection")

    run = MigrationDiscoveryRun.objects.create(
        school=connection.school,
        source_connection=connection,
        started_by=started_by,
        status=DiscoveryRunStatus.RUNNING,
    )
    record_connector_audit(
        school=connection.school,
        actor=started_by,
        event_type="discovery_started",
        source_connection=connection,
        discovery_run=run,
    )

    try:
        report = discover_entities(connection=connection)
        run.discovered_entities = report["entities"]
        run.counts_by_entity = report["counts"]
        run.warnings = report["warnings"]
        run.errors = report["errors"]
        run.external_blockers = report["external_blockers"]
        run.status = DiscoveryRunStatus.COMPLETED
        run.completed_at = timezone.now()
        run.audit_summary = {"entity_count": len(report["entities"])}
        run.save()
        record_connector_audit(
            school=connection.school,
            actor=started_by,
            event_type="discovery_completed",
            source_connection=connection,
            discovery_run=run,
            metadata={"counts": report["counts"]},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("connector_discovery failed connection=%s", str(connection.id)[:8])
        run.status = DiscoveryRunStatus.FAILED
        run.errors = [str(exc)]
        run.completed_at = timezone.now()
        run.save()
        record_connector_audit(
            school=connection.school,
            actor=started_by,
            event_type="discovery_failed",
            source_connection=connection,
            discovery_run=run,
            metadata={"error": "discovery_error"},
        )
    return run


def discover_entities(*, connection: MigrationSourceConnection) -> dict[str, Any]:
    adapter = get_connector(connection.connector_profile.key)
    credentials = retrieve_source_credential_for_runtime(connection)
    warnings: list[str] = []
    errors: list[str] = []
    external_blockers: list[str] = []
    entities: list[str] = []
    counts: dict[str, int] = {}

    if adapter is None:
        errors.append("connector_not_registered")
        return {
            "entities": entities,
            "counts": counts,
            "warnings": warnings,
            "errors": errors,
            "external_blockers": external_blockers,
        }

    caps = adapter.discover_capabilities(
        source_url=connection.source_url,
        credentials=credentials,
    )
    external_blockers.extend(caps.external_blockers)

    for entity_type in caps.supported_entities:
        if not adapter.supports_entity(entity_type):
            continue
        preview = adapter.extract_entity(
            entity_type,
            source_url=connection.source_url,
            credentials=credentials,
        )
        entities.append(entity_type)
        counts[entity_type] = preview.estimated_count
        warnings.extend(preview.warnings)

    return {
        "entities": entities,
        "counts": counts,
        "warnings": warnings,
        "errors": errors,
        "external_blockers": external_blockers,
    }


def preview_entity_counts(*, discovery_run: MigrationDiscoveryRun) -> dict[str, int]:
    return dict(discovery_run.counts_by_entity or {})


def fetch_sample_records(
    *,
    connection: MigrationSourceConnection,
    entity_type: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    adapter = get_connector(connection.connector_profile.key)
    if adapter is None:
        return []
    credentials = retrieve_source_credential_for_runtime(connection)
    preview = adapter.extract_entity(
        entity_type,
        source_url=connection.source_url,
        credentials=credentials,
        limit=limit,
    )
    return preview.sample_records


def stage_entity_preview(
    *,
    connection: MigrationSourceConnection,
    discovery_run: MigrationDiscoveryRun,
    entity_type: str,
    rows: list[dict[str, Any]],
) -> tuple[Any, list[dict[str, Any]]]:
    """Create staging batch + quarantine using migration_center helpers."""
    from apps.migration_cloud.models_connectors import (
        MigrationQuarantineItem,
        MigrationStagingBatch,
        QuarantineItemStatus,
        StagingBatchStatus,
    )

    tenant_id = str(connection.school_id)
    preview = migration_center.preview_migration(
        entity=entity_type if entity_type in migration_center.MIGRATION_TEMPLATES else "students",
        rows=rows,
        tenant_id=tenant_id,
    )
    quality = migration_center.calculate_data_quality(
        rows=rows,
        invalid_count=len(preview.get("invalid_rows", [])),
        duplicate_count=len(preview.get("duplicate_candidates", [])),
        required=migration_center.MIGRATION_TEMPLATES.get(entity_type, {}).get("required", []),
    )
    batch = MigrationStagingBatch.objects.create(
        school=connection.school,
        source_connection=connection,
        discovery_run=discovery_run,
        entity_type=entity_type,
        raw_count=len(rows),
        valid_count=max(0, len(rows) - len(preview.get("invalid_rows", []))),
        invalid_count=len(preview.get("invalid_rows", [])),
        duplicate_count=len(preview.get("duplicate_candidates", [])),
        status=StagingBatchStatus.STAGED,
        data_quality_score=Decimal(str(quality.get("score", 0))),
        staged_payload_reference=preview.get("preview_id", ""),
        staged_rows=rows,
    )
    quarantine_items = []
    for invalid in preview.get("invalid_rows", []):
        item = MigrationQuarantineItem.objects.create(
            school=connection.school,
            staging_batch=batch,
            entity_type=entity_type,
            source_identifier=str(invalid.get("row", "")),
            issue_code="missing_required",
            issue_message=str(invalid.get("reason", "")),
            raw_payload=invalid,
            status=QuarantineItemStatus.OPEN,
        )
        quarantine_items.append(item)
    return batch, quarantine_items
