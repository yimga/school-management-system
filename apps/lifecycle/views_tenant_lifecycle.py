"""Tenant-facing lifecycle views — provisioning status, fast path, launch rail API."""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

from apps.lifecycle.enrollment_workflow_matrix import build_lifecycle_workflow_hub_payload
from apps.lifecycle.launch_rail import build_launch_rail_payload
from apps.lifecycle.tenant_school_resolve import (
    can_access_tenant_lifecycle,
    lifecycle_access_denied_response,
    resolve_request_school,
)
from apps.lifecycle.unified_lifecycle import resolve_unified_lifecycle
from apps.schools.models import SchoolProvisioningEvent

logger = logging.getLogger(__name__)


def _tenant_reverse(name: str) -> str:
    try:
        return reverse(name, urlconf="config.tenant_urls")
    except NoReverseMatch:
        return reverse(name)


@login_required
def tenant_provisioning_status(request: HttpRequest) -> HttpResponse:
    """Poll-friendly provisioning page after self-serve verify or operator create."""
    school = resolve_request_school(request)
    if school is None or not can_access_tenant_lifecycle(request, school):
        return lifecycle_access_denied_response(request)

    unified = resolve_unified_lifecycle(school)
    rail = build_launch_rail_payload(school, user=request.user)
    timeline = list(
        SchoolProvisioningEvent.objects.filter(school=school)
        .order_by("-created_at")[:24]
        .values("event_type", "status", "message", "created_at")
    )

    if (
        unified.get("state") == "live"
        and not unified.get("provisioning_in_flight")
        and request.GET.get("auto") == "1"
    ):
        target = _tenant_reverse("school_studio")
        if target:
            return redirect(target)

    return render(
        request,
        "siteconfig/tenant_provisioning_status.html",
        {
            "school": school,
            "unified": unified,
            "launch_rail": rail,
            "provisioning_timeline": timeline,
            "studio_url": _tenant_reverse("school_studio"),
            "fast_path_url": _tenant_reverse("tenant_launch_fast_path"),
            "api_status_url": _tenant_reverse("api_tenant_provisioning_status"),
        },
    )


@login_required
@require_GET
def api_tenant_provisioning_status(request: HttpRequest) -> JsonResponse:
    school = resolve_request_school(request)
    if school is None or not can_access_tenant_lifecycle(request, school):
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)

    from apps.schools.provisioning_progress import resolve_provisioning_progress

    payload = resolve_provisioning_progress(
        school,
        request=request,
        include_dashboard_href=True,
    )
    rail = build_launch_rail_payload(school, user=request.user)
    payload["launch_rail_summary"] = {
        "fast_path_percent": rail.get("fast_path_percent", 0),
        "onboarding_percent": rail.get("onboarding_percent", 0),
    }
    events = list(
        SchoolProvisioningEvent.objects.filter(school=school)
        .order_by("-created_at")[:12]
        .values("event_type", "status", "created_at")
    )
    for row in events:
        ts = row.get("created_at")
        if ts is not None:
            row["created_at"] = ts.isoformat()
    payload["timeline_events"] = events
    return JsonResponse(payload)


@login_required
def tenant_launch_fast_path(request: HttpRequest) -> HttpResponse:
    """Four-step fast path to first_result (self-serve + operator)."""
    school = resolve_request_school(request)
    if school is None or not can_access_tenant_lifecycle(request, school):
        return lifecycle_access_denied_response(request)

    rail = build_launch_rail_payload(school, user=request.user)
    if rail.get("fast_path_complete") and request.GET.get("done") != "stay":
        target = _tenant_reverse("school_studio")
        if target:
            return redirect(target)

    return render(
        request,
        "siteconfig/tenant_launch_fast_path.html",
        {
            "school": school,
            "launch_rail": rail,
            "fast_path_steps": rail.get("fast_path") or [],
            "studio_url": _tenant_reverse("school_studio"),
            "provisioning_url": _tenant_reverse("tenant_provisioning_status"),
        },
    )


@login_required
@require_GET
def api_tenant_launch_rail(request: HttpRequest) -> JsonResponse:
    school = resolve_request_school(request)
    if school is None or not can_access_tenant_lifecycle(request, school):
        return JsonResponse({"ok": False}, status=403)
    rail = build_launch_rail_payload(school, user=request.user)
    return JsonResponse({"ok": True, "launch_rail": rail})


@login_required
def tenant_lifecycle_command_center(request: HttpRequest) -> HttpResponse:
    """Unified registration, enrollment, onboarding, and offboarding command center."""
    school = resolve_request_school(request)
    if school is None or not can_access_tenant_lifecycle(request, school):
        return lifecycle_access_denied_response(request)

    hub = build_lifecycle_workflow_hub_payload(school, user=request.user)
    section_nav_items = [
        {"id": "section-registration", "label": _("Registration")},
        {"id": "section-enrollment", "label": _("Enrollment")},
        {"id": "section-onboarding", "label": _("Onboarding")},
        {"id": "section-offboarding", "label": _("Offboarding")},
    ]
    onboarding_playbook_api_url = ""
    offboarding_playbook_api_url = ""
    try:
        onboarding_playbook_api_url = reverse("api:ai-onboarding-playbook")
        offboarding_playbook_api_url = reverse("api:ai-offboarding-playbook")
    except NoReverseMatch:
        pass
    return render(
        request,
        "siteconfig/tenant_lifecycle_command_center.html",
        {
            "school": school,
            "hub": hub,
            "section_nav_items": section_nav_items,
            "unified": hub.get("unified") or {},
            "launch_rail": hub.get("launch_rail") or {},
            "registration": hub.get("registration") or {},
            "enrollment": hub.get("enrollment") or {},
            "tenant_offboarding": hub.get("tenant_offboarding") or {},
            "studio_url": _tenant_reverse("school_studio"),
            "provisioning_url": _tenant_reverse("tenant_provisioning_status"),
            "fast_path_url": _tenant_reverse("tenant_launch_fast_path"),
            "offboarding_url": _tenant_reverse("tenant_offboarding"),
            "onboarding_playbook_api_url": onboarding_playbook_api_url,
            "offboarding_playbook_api_url": offboarding_playbook_api_url,
        },
    )


@login_required
@require_GET
def api_tenant_lifecycle_hub(request: HttpRequest) -> JsonResponse:
    school = resolve_request_school(request)
    if school is None or not can_access_tenant_lifecycle(request, school):
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)
    hub = build_lifecycle_workflow_hub_payload(school, user=request.user)
    return JsonResponse({"ok": True, "hub": hub})
