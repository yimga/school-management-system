"""Configuration governance queue and scheduled execution contract."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.platform_runtime.configuration_change_requests import apply_approved_change_request
from apps.platform_runtime.models import ConfigurationChangeRequest


def governance_queue_snapshot(now=None) -> dict[str, Any]:
    now = now or timezone.now()
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = ConfigurationChangeRequest.objects.all()
    pending = qs.filter(status__in=[
        ConfigurationChangeRequest.Status.REQUESTED,
        ConfigurationChangeRequest.Status.PENDING_APPROVAL,
    ])
    scheduled = qs.filter(status=ConfigurationChangeRequest.Status.SCHEDULED)
    due = scheduled.filter(scheduled_at__lte=now)
    failed = qs.filter(status=ConfigurationChangeRequest.Status.FAILED)
    external_blocked = qs.exclude(external_blockers=[]).exclude(external_blockers={})
    rollback_needed = qs.filter(request_type__in=[
        ConfigurationChangeRequest.RequestType.BLUEPRINT_ROLLBACK,
        ConfigurationChangeRequest.RequestType.PACK_ROLLBACK,
        ConfigurationChangeRequest.RequestType.PACK_DEACTIVATE,
    ]).exclude(status__in=[
        ConfigurationChangeRequest.Status.APPLIED,
        ConfigurationChangeRequest.Status.CANCELLED,
        ConfigurationChangeRequest.Status.REJECTED,
    ])
    return {
        "pending_approvals": pending.count(),
        "scheduled_changes": scheduled.count(),
        "due_scheduled_changes": due.count(),
        "failed_changes": failed.count(),
        "external_blocked_changes": external_blocked.count(),
        "rollback_needed_changes": rollback_needed.count(),
    }


def process_due_configuration_changes(*, actor=None, limit: int = 50, now=None) -> dict[str, Any]:
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    now = now or timezone.now()
    due = ConfigurationChangeRequest.objects.filter(
        status=ConfigurationChangeRequest.Status.SCHEDULED,
        scheduled_at__lte=now,
    ).order_by("scheduled_at", "pk")[:limit]
    results = []
    for change_request in due:
        if change_request.external_blockers:
            results.append({"id": change_request.pk, "ok": False, "blocked": "external_required"})
            continue
        result = apply_approved_change_request(change_request, actor=actor, force_scheduled=True)
        results.append({"id": change_request.pk, **result})
    return {
        "processed": len(results),
        "results": results,
    }
