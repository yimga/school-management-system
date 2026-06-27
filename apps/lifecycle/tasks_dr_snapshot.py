"""Celery tasks for tenant immutable DR snapshots."""

from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="lifecycle.capture_tenant_immutable_snapshots_daily", ignore_result=True)
def capture_tenant_immutable_snapshots_daily() -> int:
    from apps.lifecycle.tenant_dr_snapshot import capture_daily_snapshot
    from apps.schools.models import School

    count = 0
    for school in School.objects.filter(is_active=True, deleted_at__isnull=True).iterator():
        try:
            capture_daily_snapshot(school)
            count += 1
        except Exception:
            logger.warning(
                "tenant_dr_snapshot.capture_failed school_id=%s",
                getattr(school, "pk", "?"),
                exc_info=True,
            )
    return count


@shared_task(name="lifecycle.verify_tenant_snapshot_restore_integrity", ignore_result=True)
def verify_tenant_snapshot_restore_integrity(school_id: str) -> dict:
    """Real (non-dry-run) restore drill for one tenant's latest snapshot.

    Unlike ``scripts/restore_drill.py`` (which exercises the *cloud-backup*
    runbook in dry-run), this task performs an ACTUAL application-level restore
    of the most recent immutable snapshot — signature-verified, then
    materialized — inside a transaction that is ALWAYS rolled back, so it proves
    the restore path works end-to-end without mutating production.

    Returns a dict with ``ok`` plus the per-table created/updated counts and the
    snapshot's recorded aggregate counts so the operator can compare.
    """
    from django.db import transaction

    from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot
    from apps.lifecycle.tenant_dr_snapshot import restore_from_snapshot

    row = (
        TenantImmutableSnapshot.objects.filter(school_id=school_id)
        .order_by("-snapshot_date", "-created_at")
        .first()
    )
    if row is None:
        logger.warning("tenant_dr_snapshot.no_snapshot school_id=%s", school_id)
        return {"ok": False, "reason": "no_snapshot", "school_id": str(school_id)}

    class _Rollback(Exception):
        pass

    result: dict = {"ok": False, "school_id": str(school_id), "snapshot_id": str(row.pk)}
    try:
        with transaction.atomic():
            payload = restore_from_snapshot(
                Path(row.primary_uri),
                school_id=str(school_id),
                expected_sig=row.signature_hex,
            )
            result["counts"] = payload.get("counts")
            result["restored"] = payload.get("restored")
            result["ok"] = True
            # Never persist the drill restore — it is a verification, not a real
            # recovery. Roll back the whole transaction.
            raise _Rollback()
    except _Rollback:
        pass
    except (ValueError, OSError):
        logger.warning(
            "tenant_dr_snapshot.restore_integrity_failed school_id=%s snapshot_id=%s",
            school_id,
            row.pk,
            exc_info=True,
        )
        result["ok"] = False
        result["reason"] = "restore_error"

    logger.info(
        "tenant_dr_snapshot.restore_integrity school_id=%s ok=%s",
        school_id,
        result["ok"],
    )
    return result
