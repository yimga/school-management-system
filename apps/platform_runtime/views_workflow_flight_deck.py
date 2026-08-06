"""Workflow Flight Deck — operator mission control (10x wave 3)."""

from __future__ import annotations

import json


from apps.schools.control_plane import require_control_plane_access
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
        "healing_count": _("Healing"),
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
        "action_success": _("Action completed."),
        "action_unreachable": _(
            "Couldn't reach the server — it may be restarting. Try again in a moment."
        ),
        "action_unavailable": _(
            "This action isn't available for this run — open run detail or Tenant 360."
        ),
        "action_requires_network": _(
            "Requires network — retry when connected."
        ),
        "preview_title": _("Fix preview"),
        "clear_after_success": _("Clear from deck"),
        "clear_requires_success": _(
            "Can only clear after provisioning has succeeded."
        ),
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
        "stream": reverse("platform_runtime:workflow_progress_stream"),
        "healing_status": reverse(
            "platform_runtime:workflow_progress_healing_status",
            kwargs={"run_id": 0},
        ).replace("/0/", "/{run_id}/"),
    }


@require_control_plane_access
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
    # Cross-link to the OTHER workflow observability plane — the orchestration
    # workbench (OrchestrationRun business processes), a different object than the
    # @track_workflow platform runs shown here. Guarded so it degrades if unrouted.
    from django.urls import NoReverseMatch

    orchestration_workbench_url = ""
    try:
        orchestration_workbench_url = reverse("super:orchestration_workbench")
    except NoReverseMatch:
        pass
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
            "orchestration_workbench_url": orchestration_workbench_url,
        },
    )


@login_required_api
@require_GET
def flight_deck_json_view(request):
    """JSON payload for Flight Deck UI + copilot context."""

    from apps.platform_runtime.models import WorkflowRun
    from apps.platform_runtime.workflow_flight_deck_actions import enrich_run_payload
    from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated
    from apps.platform_runtime.workflow_incident_actions import enrich_incident_row
    from apps.platform_runtime.workflow_incidents import cluster_recent_incidents
    from apps.platform_runtime.workflow_recovery_playbook import (
        recovery_coverage_gaps,
        workflow_recovery_coverage,
    )
    from apps.platform_runtime.workflow_status_taxonomy import status_taxonomy_payload
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
        run = active_run_map.get(row.get("id"))
        if run is not None and workflow_run_is_remediated(run):
            continue
        active.append(enrich_run_payload(row, run=run))

    from apps.platform_runtime.tasks import suppress_stale_provision_failure_for_deck

    recent_failed = []
    qs = WorkflowRun.objects.filter(  # tenant-isolation-allow: operator-flight-deck-recent-failed-tenant-schema-filter
        status__in=("failed", "cancelled")
    ).order_by("-ended_at")[:60]
    if schema:
        qs = qs.filter(tenant_schema=schema)
    for run in qs:
        if workflow_run_is_remediated(run):
            continue
        # Provision success (or a newer attempt) must not leave historical FAILED
        # cards inflating Needs operator — stamp + hide immediately on read.
        if suppress_stale_provision_failure_for_deck(run):
            continue
        recent_failed.append(
            enrich_run_payload(serialize_workflow_run(run), run=run)
        )
        if len(recent_failed) >= 20:
            break

    incidents = [
        enrich_incident_row(row)
        for row in (cluster_recent_incidents() if is_staff and not schema else [])
    ]

    stuck_count = sum(1 for r in active if r.get("status") == "stuck")
    stopped_count = sum(
        1 for r in recent_failed if r.get("status") in ("failed", "cancelled", "stopped")
    )
    needs_operator = sum(
        1
        for r in (*active, *recent_failed)
        if r.get("operator_actions")
        and any(
            a.get("kind") in ("apply_fix", "requeue_provision", "cancel")
            for a in r.get("operator_actions") or []
        )
    )
    healing_count = sum(
        1
        for r in (*active, *recent_failed)
        if (r.get("healing_session") or {}).get("session_id")
        and str((r.get("healing_session") or {}).get("phase") or "")
        not in ("succeeded", "failed", "cancelled", "")
    )
    from apps.platform_runtime.workflow_healing_chains import healing_coverage_report

    healing_report = healing_coverage_report()
    recovery_coverage = workflow_recovery_coverage()
    coverage_gaps = recovery_coverage_gaps()

    return JsonResponse(
        {
            "generated_at": timezone.now().isoformat(),
            "endpoints": _flight_deck_endpoints(),
            "labels": flight_deck_labels(),
            "status_taxonomy": status_taxonomy_payload(),
            "active": active,
            "recent_failed": recent_failed,
            "incidents": incidents,
            "summary": {
                "active_count": len(active),
                "failed_count": len(recent_failed),
                "stuck_count": stuck_count,
                "stopped_count": stopped_count,
                "needs_operator_count": needs_operator,
                "healing_count": healing_count,
            },
            "copilot_context": {
                "active_run_ids": [r.get("id") for r in active if r.get("id")],
                "failed_run_ids": [r.get("id") for r in recent_failed if r.get("id")],
                "stuck_count": stuck_count,
                "stopped_count": stopped_count,
                "degrading_count": sum(1 for r in active if r.get("status") == "degrading"),
                "needs_operator_count": needs_operator,
                "status_taxonomy": status_taxonomy_payload(),
                "recovery_coverage": {
                    "workflow_count": len(recovery_coverage),
                    "gap_count": len(coverage_gaps),
                    "gap_keys": coverage_gaps,
                },
                "healing_coverage": {
                    "workflow_count": healing_report.get("workflow_count", 0),
                    "gap_count": healing_report.get("gap_count", 0),
                },
                "recovery_queue": [
                    r.get("copilot_recovery_context")
                    for r in (*active, *recent_failed)
                    if r.get("copilot_recovery_context")
                ][:25],
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
