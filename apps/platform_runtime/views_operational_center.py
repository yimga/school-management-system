"""Implementation, support, pilot evidence, and defect dashboards (operator hub)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

from apps.accounts.permissions import tenant_operator_hub_eligible
from apps.schools.control_plane import user_has_control_plane_access
from apps.schools.models import School

from apps.platform_runtime.implementation_checklist import build_implementation_checklist
from apps.platform_runtime.operator_adoption_metrics import compute_operator_adoption_metrics
from apps.platform_runtime.pilot_defect_closure import (
    dashboard_bucket,
    load_defects,
    sort_defects_for_dashboard,
)
from apps.platform_runtime.pilot_evidence import build_pilot_dashboard_rows


def _log_surface_event(request, event_type: str, school: School | None) -> None:
    try:
        from apps.platform_runtime.models import PlatformEventLog

        PlatformEventLog.objects.create(
            event_type=event_type,
            school_id=str(school.pk) if school else "",
            payload={"path": getattr(request, "path", "")[:512]},
        )
    except (
        ImportError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        pass


def _resolve_target_school(request):
    """Platform operators may pass ?school_slug=; tenant hub uses request.school."""
    if user_has_control_plane_access(request.user):
        slug = (request.GET.get("school_slug") or "").strip()
        if slug:
            return get_object_or_404(School, slug=slug)
        return None
    return getattr(request, "school", None)


def _operational_access(request):
    if user_has_control_plane_access(request.user):
        return True
    school = getattr(request, "school", None)
    return bool(
        request.user.is_authenticated
        and school is not None
        and tenant_operator_hub_eligible(request.user)
    )


def _playbooks_context() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "data" / "support_playbooks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    playbooks = data.get("playbooks") or []
    enriched = []
    for p in playbooks:
        row = dict(p)
        pa = row.get("primary_action") or {}
        url_name = pa.get("url_name")
        url = ""
        if url_name:
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                url = ""
        row["primary_action_url"] = url
        enriched.append(row)
    return {"playbooks": enriched}


@login_required
def implementation_command_center(request):
    if not _operational_access(request):
        return HttpResponseForbidden("Not allowed.")
    school = _resolve_target_school(request)
    _log_surface_event(request, "implementation_command_center_viewed", school)
    checklist = build_implementation_checklist(school)
    school_ids = [school.pk] if school else []
    metrics = compute_operator_adoption_metrics(school_ids)
    return render(
        request,
        "platform_runtime/implementation_command_center.html",
        {
            "school": school,
            "checklist_items": checklist["items"],
            "primary_next_action": checklist["primary_next_action"],
            "go_live_readiness_score": checklist.get("go_live_readiness_score", 0),
            "go_live_readiness_band": checklist.get("go_live_readiness_band", ""),
            "consolidated_blockers": checklist.get("consolidated_blockers", []),
            "adoption_metrics": metrics,
            "page_marker": "rmc-implementation-command-center",
        },
    )


@login_required
@require_GET
def implementation_missing_data_blockers_json(request):
    """
    Consolidated missing/partial checklist blockers (same RBAC as command center).
    """
    if not _operational_access(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    school = _resolve_target_school(request)
    checklist = build_implementation_checklist(school)
    return JsonResponse(
        {
            "school_slug": getattr(school, "slug", None),
            "go_live_readiness_score": checklist.get("go_live_readiness_score"),
            "go_live_readiness_band": checklist.get("go_live_readiness_band"),
            "go_live_readiness_weights_version": checklist.get(
                "go_live_readiness_weights_version"
            ),
            "missing_count": checklist.get("missing_count"),
            "partial_count": checklist.get("partial_count"),
            "blockers": checklist.get("consolidated_blockers", []),
            "primary_next_action": checklist.get("primary_next_action"),
        }
    )


@login_required
def support_playbook_center(request):
    if not _operational_access(request):
        return HttpResponseForbidden("Not allowed.")
    school = getattr(request, "school", None)
    _log_surface_event(request, "support_playbook_center_viewed", school)
    ctx = _playbooks_context()
    ctx["page_marker"] = "rmc-support-playbook-center"
    return render(request, "platform_runtime/support_playbook_center.html", ctx)


@login_required
def pilot_evidence_dashboard(request):
    if not _operational_access(request):
        return HttpResponseForbidden("Not allowed.")
    ctx = build_pilot_dashboard_rows()
    ctx["page_marker"] = "rmc-pilot-evidence-dashboard"
    return render(request, "platform_runtime/pilot_evidence_dashboard.html", ctx)


@login_required
def pilot_defect_dashboard(request):
    if not _operational_access(request):
        return HttpResponseForbidden("Not allowed.")
    defects = load_defects()
    ctx = {
        "defects": sort_defects_for_dashboard(defects),
        "buckets": dashboard_bucket(defects),
        "page_marker": "rmc-pilot-defect-dashboard",
    }
    return render(request, "platform_runtime/pilot_defect_dashboard.html", ctx)
