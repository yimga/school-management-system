"""Workflow Flight Deck — operator mission control (10x wave 3)."""

from __future__ import annotations

import json


from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from services.http_auth_guards import login_required_api

from apps.platform_runtime.views_workflow_progress import _resolve_scope


def flight_deck_labels() -> dict[str, str]:
    return {
        "summary": _("Summary"),
        "active": _("Active"),
        "recent_failures": _("Recent failures"),
        "cross_tenant_signals": _("Cross-tenant signals"),
        "active_count": _("Active"),
        "failed_count": _("Recent failures"),
        "needs_operator_count": _("Needs operator"),
        "no_runs": _("No runs."),
        "no_incidents": _("No correlated incidents."),
        "no_actions": _(
            "No automated fix available — inspect run detail or Tenant 360."
        ),
        "load_error": _("Could not load Flight Deck."),
        "action_failed": _("Action failed"),
        "runs_label": _("runs"),
        "tenants_label": _("tenants"),
        "bulk_apply_fix": _("Apply fix to all eligible runs"),
        "bulk_apply_progress": _("Applying fixes…"),
        "bulk_apply_done": _("Bulk apply finished."),
    }


def _flight_deck_endpoints() -> dict[str, str]:
    return {
        "apply_fix": reverse(
            "platform_runtime:workflow_progress_apply_fix",
            kwargs={"run_id": 0},
        ).replace("/0/", "/{run_id}/"),
        "cancel": reverse(
            "platform_runtime:workflow_progress_cancel",
            kwargs={"run_id": 0},
        ).replace("/0/", "/{run_id}/"),
        "requeue_provision": reverse(
            "super:api_school_requeue_provision",
            kwargs={"school_id": "00000000-0000-0000-0000-000000000000"},
        ).replace("00000000-0000-0000-0000-000000000000", "{school_id}"),
        "bulk_apply": reverse("platform_runtime:workflow_progress_incident_bulk_apply"),
    }


@staff_member_required
@require_GET
def flight_deck_view(request):
    """Full-page operator workflow command center."""

    from apps.platform_runtime.super_operational_frames import resolve_super_operational_frame

    frame = resolve_super_operational_frame(
        "workflow_flight_deck",
        center_title="Workflow Flight Deck",
        center_purpose="Live mission control for platform workflows, cross-tenant incidents, and autopilot fixes.",
        status_badge_text="Live",
        primary_url=reverse("platform_runtime:workflow_progress_flight_deck"),
        primary_label="Refresh deck",
    )
    return render(
        request,
        "platform_runtime/workflow_flight_deck.html",
        {
            **frame,
            "page_title": "Workflow Flight Deck",
            "flight_deck_api_url": reverse("platform_runtime:workflow_progress_flight_deck_json"),
            "flight_deck_page_url": reverse("platform_runtime:workflow_progress_flight_deck"),
            "flight_deck_endpoints_json": json.dumps(_flight_deck_endpoints()),
            "flight_deck_labels": flight_deck_labels(),
        },
    )


@login_required_api
@require_GET
def flight_deck_json_view(request):
    """JSON payload for Flight Deck UI + copilot context."""

    from apps.platform_runtime.models import WorkflowRun
    from apps.platform_runtime.workflow_flight_deck_actions import enrich_run_payload
    from apps.platform_runtime.workflow_incident_actions import enrich_incident_row
    from apps.platform_runtime.workflow_incidents import cluster_recent_incidents
    from apps.platform_runtime.workflow_tracker import list_active_runs, serialize_workflow_run

    schema, actor_id = _resolve_scope(request)
    is_staff = bool(getattr(request.user, "is_staff", False))
    if not is_staff:
        return JsonResponse({"error": "forbidden"}, status=403)

    active_rows = list(list_active_runs(tenant_schema=schema, actor_user_id="", limit=50))
    active_ids = [row.get("id") for row in active_rows if row.get("id")]
    active_run_map = {
        run.pk: run
        for run in WorkflowRun.objects.filter(  # tenant-isolation-allow: flight-deck-batch-enrich-by-pk-list
            pk__in=active_ids
        )
    }
    active = []
    for row in active_rows:
        active.append(enrich_run_payload(row, run=active_run_map.get(row.get("id"))))

    recent_failed = []
    qs = WorkflowRun.objects.filter(  # tenant-isolation-allow: operator-flight-deck-recent-failed-tenant-schema-filter
        status__in=("failed", "cancelled")
    ).order_by("-ended_at")[:20]
    if schema:
        qs = qs.filter(tenant_schema=schema)
    for run in qs:
        recent_failed.append(
            enrich_run_payload(serialize_workflow_run(run), run=run)
        )

    incidents = [
        enrich_incident_row(row)
        for row in (cluster_recent_incidents() if is_staff and not schema else [])
    ]

    stuck_count = sum(1 for r in active if r.get("status") == "stuck")
    needs_operator = sum(
        1
        for r in (*active, *recent_failed)
        if r.get("operator_actions")
        and any(
            a.get("kind") in ("apply_fix", "requeue_provision", "cancel")
            for a in r.get("operator_actions") or []
        )
    )

    return JsonResponse(
        {
            "generated_at": timezone.now().isoformat(),
            "endpoints": _flight_deck_endpoints(),
            "labels": flight_deck_labels(),
            "active": active,
            "recent_failed": recent_failed,
            "incidents": incidents,
            "summary": {
                "active_count": len(active),
                "failed_count": len(recent_failed),
                "stuck_count": stuck_count,
                "needs_operator_count": needs_operator,
            },
            "copilot_context": {
                "active_run_ids": [r.get("id") for r in active if r.get("id")],
                "stuck_count": stuck_count,
                "degrading_count": sum(1 for r in active if r.get("status") == "degrading"),
                "needs_operator_count": needs_operator,
            },
        }
    )


@login_required_api
@require_POST
def incident_bulk_apply_view(request):
    """Apply auto-fix to all eligible runs in a cross-tenant incident cluster."""

    if not bool(getattr(request.user, "is_staff", False)):
        return JsonResponse({"error": "forbidden"}, status=403)

    remediation_key = (
        request.POST.get("remediation_key")
        or request.GET.get("remediation_key")
        or ""
    ).strip()
    from apps.platform_runtime.workflow_incident_actions import (
        bulk_apply_incident_remediation,
    )

    result = bulk_apply_incident_remediation(
        remediation_key=remediation_key,
        actor_user_id=str(getattr(request.user, "id", "") or ""),
    )
    status = 200 if result.get("ok") or result.get("skipped") else 400
    if result.get("reason") == "missing_remediation_key":
        status = 400
    return JsonResponse(result, status=status)
