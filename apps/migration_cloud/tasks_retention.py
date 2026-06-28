"""v3.40.0 Agent 15 — monthly retention audit Celery task.

This task is the *informational* counterpart to the mutating
``purge_completed_migration_bundles`` management command. It runs in
**DRY-RUN ONLY** mode on the first of each month and reports the
candidate counts to the operator alert channel at ``severity="info"``
(audit-only; never warns the on-call rotation because the audit pass
is not actionable on its own — the operator must run the management
command with counsel signoff to actually purge).

The task NEVER calls ``--apply``. It NEVER logs tenant slugs, blob
ids, or file paths. Only counts + sha256 prefixes appear in alerts
or logs.

Wired from ``config/settings.py::CELERY_BEAT_SCHEDULE`` as
``migration-cloud-retention-audit-monthly``.
"""
from __future__ import annotations

import logging
from typing import Any

try:
    from celery import shared_task
except Exception:  # pragma: no cover — celery absent in some lanes
    def shared_task(*args, **kwargs):  # type: ignore[no-redef]
        def _decorator(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return _decorator

logger = logging.getLogger(__name__)


def _safe_alert_info(*, title: str, body: str, dedupe_key: str) -> None:
    """Defensive wrapper around ``apps.migration_cloud.alerts.alert``.

    Agent 12 owns the alert surface; we import it lazily so this task
    stays importable even if alerts.py is mid-deploy. Channel failure
    is swallowed; we still log structured.
    """
    try:
        from apps.migration_cloud.alerts import alert
        alert(
            severity="info",
            title=title,
            body=body,
            dedupe_key=dedupe_key,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud_retention_audit_alert_failed err_type=%s",
            type(exc).__name__,
        )


def _audit_tenant(tenant, default_days: int) -> dict[str, Any]:
    """Return ``{candidates, total_bytes, tenant_id}`` for one tenant.

    Calls into the same candidate-collection logic the management
    command uses, but never mutates and never calls ``--apply``.
    Defensive: missing models / unhappy DB returns zero counts.
    """
    out: dict[str, Any] = {
        "tenant_id": getattr(tenant, "pk", None),
        "candidates": 0,
        "total_bytes": 0,
    }
    try:
        import datetime as _dt
        from django.utils import timezone

        from apps.migration_cloud.models import CompanionCiphertextBlob

        cutoff = timezone.now() - _dt.timedelta(days=default_days)
        # tenant-isolation-allow: retention-audit-task-dry-run-per-tenant
        qs = CompanionCiphertextBlob.objects.filter(
            tenant_id=tenant.pk,
            received_at__lt=cutoff,
            decrypted_at__isnull=False,
        ).only("byte_size")
        candidates = list(qs)
        out["candidates"] = len(candidates)
        out["total_bytes"] = int(
            sum(int(getattr(b, "byte_size", 0) or 0) for b in candidates)
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud_retention_audit_tenant_failed "
            "tenant_id=%s err_type=%s",
            getattr(tenant, "pk", "?"), type(exc).__name__,
        )
    return out


@shared_task(name="apps.migration_cloud.tasks_retention.purge_completed_migration_bundles_audit_task")
def purge_completed_migration_bundles_audit_task() -> dict[str, Any]:
    """Monthly DRY-RUN audit of retention-eligible ciphertext blobs.

    Returns a small summary dict (useful for tests + ad-hoc invocation
    via ``celery call``). Emits one info-level alert per tenant whose
    candidate count is non-zero.
    """
    from django.conf import settings

    default_days = int(
        getattr(settings, "MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS", 180)
        or 180
    )

    summary: dict[str, Any] = {
        "tenants_audited": 0,
        "tenants_with_candidates": 0,
        "total_candidates": 0,
        "total_bytes": 0,
        "default_days": default_days,
    }

    try:
        from apps.schools.models import School
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud_retention_audit_schools_import_failed err_type=%s",
            type(exc).__name__,
        )
        return summary

    try:
        # tenant-isolation-allow: retention-audit-task-platform-wide-tenant-sweep
        tenants = list(School.objects.all().only("id", "slug"))
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud_retention_audit_tenant_sweep_failed err_type=%s",
            type(exc).__name__,
        )
        return summary

    for tenant in tenants:
        summary["tenants_audited"] += 1
        result = _audit_tenant(tenant, default_days)
        if result["candidates"] > 0:
            summary["tenants_with_candidates"] += 1
            summary["total_candidates"] += int(result["candidates"])
            summary["total_bytes"] += int(result["total_bytes"])
            _safe_alert_info(
                title=(
                    f"Migration Cloud retention audit: tenant #"
                    f"{result['tenant_id']} has "
                    f"{result['candidates']} purge-eligible bundles"
                ),
                body=(
                    f"DRY-RUN audit: {result['candidates']} bundles "
                    f"({result['total_bytes']} bytes) older than "
                    f"{default_days} days are eligible for retention "
                    f"purge. Operator action required via "
                    f"`python manage.py purge_completed_migration_bundles`."
                ),
                dedupe_key=(
                    f"retention-audit-tenant-{result['tenant_id']}"
                ),
            )

    logger.info(
        "migration_cloud_retention_audit_completed "
        "tenants_audited=%s tenants_with_candidates=%s "
        "total_candidates=%s total_bytes=%s default_days=%s",
        summary["tenants_audited"],
        summary["tenants_with_candidates"],
        summary["total_candidates"],
        summary["total_bytes"],
        default_days,
    )
    return summary
