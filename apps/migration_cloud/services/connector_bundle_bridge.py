"""Bridge connector staging rows into MigrationBundle ingest + apply pipeline."""

from __future__ import annotations

import csv
import logging
import tempfile
from pathlib import Path
from typing import Any

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.orchestrator import apply_bundle
from apps.migration_cloud.pipeline import advance_bundle
from apps.migration_cloud.services import BundleIngestionService, BundleSpec

logger = logging.getLogger(__name__)


def _school_schema_name(school) -> str:
    from apps.migration_cloud.schema_binding import resolve_school_schema_name

    # Never fall back to slug — production schemas are s_<uuid-hex>, not slug.
    return resolve_school_schema_name(school) or "public"


def write_staging_csv(
    *,
    rows: list[dict[str, Any]],
    entity_type: str,
) -> Path:
    """Write staged rows to a temp CSV file for file intake."""
    if not rows:
        rows = [{"note": "empty_staging_placeholder"}]
    tmp = Path(tempfile.mkdtemp(prefix="rmc-connector-"))
    path = tmp / f"{entity_type}.csv"
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def ingest_staged_csv_to_bundle(
    *,
    csv_path: Path,
    school,
    idempotency_key: str,
    source_hint: str,
    label: str,
    triggered_by_id: int | None,
) -> tuple[MigrationBundle, int]:
    """Create/reuse bundle and register the CSV artifact."""
    svc = BundleIngestionService()
    result = svc.ingest(
        BundleSpec(
            intake_method=IntakeMethod.FILE_UPLOAD,
            handle=csv_path,
            school_id=school.pk,
            schema_name=_school_schema_name(school),
            label=label,
            source_hint=source_hint,
            idempotency_key=idempotency_key,
            triggered_by_id=triggered_by_id,
            intake_source_uri=str(csv_path),
        )
    )
    bundle = MigrationBundle.objects.get(pk=result.bundle_id)  # tenant-isolation-allow: connector-ingest-bundle-pk
    return bundle, result.artifacts_registered


def run_bundle_pipeline(
    *,
    bundle_id: int,
    source_hint: str = "",
    use_accelerator: bool = True,
    dry_run_apply: bool = False,
) -> dict[str, Any]:
    """Advance bundle to MAPPED then apply via orchestrator."""
    bundle = MigrationBundle.objects.get(pk=bundle_id)  # tenant-isolation-allow: connector-bridge-pk
    if source_hint and not bundle.source_hint:
        bundle.source_hint = source_hint
        bundle.save(update_fields=["source_hint", "updated_at"])

    advance_summary = advance_bundle(bundle_id=bundle_id, use_accelerator=use_accelerator)
    bundle.refresh_from_db()

    apply_summary: dict[str, Any] = {"skipped": True, "reason": "not_mapped"}
    if bundle.status == BundleStatus.MAPPED:
        apply_result = apply_bundle(bundle_id=bundle_id, dry_run=dry_run_apply)
        apply_summary = {
            "dry_run": apply_result.dry_run,
            "status": apply_result.status,
            "total_created": apply_result.total_created,
            "total_updated": apply_result.total_updated,
            "total_quarantined": apply_result.total_quarantined,
        }
    elif bundle.status == BundleStatus.FAILED:
        apply_summary = {"skipped": True, "reason": "bundle_failed"}

    bundle.refresh_from_db()
    return {
        "bundle_id": bundle_id,
        "bundle_status": bundle.status,
        "advance": advance_summary,
        "apply": apply_summary,
    }
