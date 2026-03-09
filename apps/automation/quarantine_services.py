"""
Repair and quarantine: add records to quarantine, mark repaired, replay repaired subset.
"""
from __future__ import annotations

from django.utils import timezone

from .models import MigrationQuarantineRecord, MigrationRun


def add_to_quarantine(
    *,
    school=None,
    migration_run=None,
    domain: str,
    row_index: int,
    payload: dict,
    issue_class: str,
) -> MigrationQuarantineRecord:
    """Record a row that failed validation or needs repair."""
    return MigrationQuarantineRecord.objects.create(
        school=school,
        migration_run=migration_run,
        domain=domain,
        row_index=row_index,
        payload=payload,
        issue_class=issue_class,
        status=MigrationQuarantineRecord.Status.PENDING,
    )


def mark_repaired(record: MigrationQuarantineRecord, resolution_payload: dict) -> None:
    """Mark a quarantine record as repaired with the resolved row data."""
    record.status = MigrationQuarantineRecord.Status.REPAIRED
    record.resolution_payload = resolution_payload
    record.resolved_at = timezone.now()
    record.save(update_fields=["status", "resolution_payload", "resolved_at"])


def get_repaired_rows(school=None, domain: str = None, migration_run=None) -> list[dict]:
    """Return list of repaired row payloads (resolution_payload or payload) for replay."""
    qs = MigrationQuarantineRecord.objects.filter(status=MigrationQuarantineRecord.Status.REPAIRED)
    if school is not None:
        qs = qs.filter(school=school)
    if domain:
        qs = qs.filter(domain=domain)
    if migration_run is not None:
        qs = qs.filter(migration_run=migration_run)
    rows = []
    for rec in qs.order_by("row_index"):
        rows.append(rec.resolution_payload if rec.resolution_payload else rec.payload)
    return rows
