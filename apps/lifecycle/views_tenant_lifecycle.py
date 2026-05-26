"""Tenant-facing lifecycle views — provisioning status, fast path, launch rail API."""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

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

    unified = resolve_unified_lifecycle(school)
    events = list(
        SchoolProvisioningEvent.objects.filter(school=school)
        .order_by("-created_at")[:12]
        .values("event_type", "status", "created_at")
    )
    for row in events:
        ts = row.get("created_at")
        if ts is not None:
            row["created_at"] = ts.isoformat()
    rail = build_launch_rail_payload(school, user=request.user)
    payload = {
        "ok": True,
        "unified": unified,
        "events": events,
        "launch_rail_summary": {
            "fast_path_percent": rail.get("fast_path_percent", 0),
            "onboarding_percent": rail.get("onboarding_percent", 0),
        },
    }
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
