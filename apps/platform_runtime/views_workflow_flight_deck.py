"""Workflow Flight Deck — operator mission control (10x wave 3)."""

from __future__ import annotations

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET
from services.http_auth_guards import login_required_api

from apps.platform_runtime.views_workflow_progress import _resolve_scope


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
        },
    )


@login_required_api
@require_GET
def flight_deck_json_view(request):
    """JSON payload for Flight Deck UI + copilot context."""

    from apps.platform_runtime.models import WorkflowRun
    from apps.platform_runtime.workflow_incidents import cluster_recent_incidents
    from apps.platform_runtime.workflow_tracker import list_active_runs, serialize_workflow_run

    schema, actor_id = _resolve_scope(request)
    is_staff = bool(getattr(request.user, "is_staff", False))
    if not is_staff:
        return JsonResponse({"error": "forbidden"}, status=403)

    active = list_active_runs(tenant_schema=schema, actor_user_id="", limit=50)
    recent_failed = []
    qs = WorkflowRun.objects.filter(status__in=("failed", "cancelled")).order_by("-ended_at")[:20]
    if schema:
        qs = qs.filter(tenant_schema=schema)
    for run in qs:
        recent_failed.append(serialize_workflow_run(run))

    incidents = cluster_recent_incidents() if is_staff and not schema else []

    return JsonResponse(
        {
            "generated_at": timezone.now().isoformat(),
            "active": active,
            "recent_failed": recent_failed,
            "incidents": incidents,
            "copilot_context": {
                "active_run_ids": [r.get("id") for r in active if r.get("id")],
                "stuck_count": sum(1 for r in active if r.get("status") == "stuck"),
                "degrading_count": sum(1 for r in active if r.get("status") == "degrading"),
            },
        }
    )
