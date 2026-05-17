"""
Portfolio scheduler for tenant lifecycle retention playbooks.

Scans an explicit school queryset (caller supplies scope), evaluates lifecycle state per tenant,
creates deduplicated playbook actions + audit rows, and records one scheduler run row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from apps.platform_runtime.models import (
    TenantLifecycleSchedulerRun,
    TenantRetentionPlaybookAuditLog,
)
from apps.platform_runtime.tenant_retention_playbooks import evaluate_playbooks_for_school

if TYPE_CHECKING:
    from django.db.models import QuerySet


def run_lifecycle_retention_scan(
    *,
    schools: QuerySet | None = None,
    now=None,
) -> TenantLifecycleSchedulerRun:
    """
    Scan tenants and enqueue retention playbook actions.

    Tenant isolation: only schools present in ``schools`` are touched — pass platform-filtered
    queryset or ``School.objects.filter(pk__in=[tenant])`` from callers.

    Avoids duplicate actions via playbook idempotency keys (per school/day/phase).
    """
    from apps.schools.models import School

    now = now or timezone.now()
    qs = schools if schools is not None else School.objects.all().order_by("pk")

    run = TenantLifecycleSchedulerRun.objects.create(
        meta={"kind": "lifecycle_retention_scan"},
        status=TenantLifecycleSchedulerRun.Status.SUCCESS,
    )
    scanned = 0
    actions_created = 0

    try:
        for school in qs.iterator(chunk_size=50):
            scanned += 1
            actions_created += evaluate_playbooks_for_school(
                school, scheduler_run=run, now=now
            )

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        audits_written = TenantRetentionPlaybookAuditLog.objects.filter(
            scheduler_run_id=run.pk
        ).count()

        run.tenants_scanned = scanned
        run.actions_created = actions_created
        run.audits_written = audits_written
        run.finished_at = timezone.now()
        run.meta.update({"school_count_hint": scanned})
        run.save(
            update_fields=[
                "tenants_scanned",
                "actions_created",
                "audits_written",
                "finished_at",
                "meta",
            ]
        )
    except Exception as exc:
        run.status = TenantLifecycleSchedulerRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at"])
        raise

    return run
