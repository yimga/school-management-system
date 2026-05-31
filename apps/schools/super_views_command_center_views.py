"""
Mission control / command center HTML views (BR-12 split from super_views).
"""

from __future__ import annotations

from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from apps.platform_runtime.models import PlatformOperatorCommandCenterLink
from apps.siteconfig.models_feature_controls import GlobalSupportTicket

from .models import School
from .super_dashboard_cache import (
    get_cached_command_center_data,
    get_cached_platform_health,
)
from .super_views_helpers import safe_platform_incidents_url
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_command_center(request):
    """
    Phase 3 mission-control surface combining approvals, billing, support, and risk posture.
    """
    if request.method == "POST":
        return HttpResponseRedirect(request.get_full_path() or reverse("super:command_center"))
    command_center = get_cached_command_center_data()
    pending_schools = list(
        School.objects.filter(is_approved=False)
        .order_by("-created_at")
        .annotate(student_count=Count("student_profiles", distinct=True))[:30]
    )
    trial_schools = list(
        School.objects.filter(
            is_active=True, billing_type=School.BillingType.FREE_TRIAL
        ).order_by("trial_end_date", "name")[:30]
    )
    stale_support = command_center.get("support_stale_rows", [])[:20]
    provisioning_breach_rows = command_center.get("provisioning_breach_rows", [])[:20]

    school_map = {
        school.id: school
        for school in School.objects.filter(
            id__in=[row["school_id"] for row in provisioning_breach_rows]
        ).only("id", "name", "slug")
    }
    for row in provisioning_breach_rows:
        row["school"] = school_map.get(row["school_id"])

    operator_command_center_links = list(
        PlatformOperatorCommandCenterLink.objects.order_by("sort_order", "slug")
    )
    return render(
        request,
        "schools/super_command_center.html",
        {
            "command_center": command_center,
            "pending_schools": pending_schools,
            "trial_schools": trial_schools,
            "stale_support": stale_support,
            "provisioning_breach_rows": provisioning_breach_rows,
            "support_dashboard_url": reverse("super:support_dashboard"),
            "billing_dashboard_url": reverse("super:billing_dashboard"),
            "usage_url": reverse("super:usage"),
            "dashboard_url": reverse("super:dashboard"),
            "open_ticket_statuses": list(GlobalSupportTicket.Status.values),
            "operator_command_center_links": operator_command_center_links,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_command_center_v2(request):
    """Operational queue drill-down for the manager control plane."""
    if request.method == "POST":
        return HttpResponseRedirect(
            request.get_full_path() or reverse("super:command_center")
        )
    from apps.billing.models import TenantSubscription
    from apps.events.legacy_bridge import legacy_webhook_sync_snapshot
    from apps.observability.models import PlatformIncident

    command_center = get_cached_command_center_data()
    pending_schools = list(
        School.objects.filter(is_approved=False)
        .order_by("-created_at")
        .annotate(student_count=Count("student_profiles", distinct=True))[:30]
    )
    trial_schools = list(
        School.objects.filter(
            is_active=True, billing_type=School.BillingType.FREE_TRIAL
        ).order_by("trial_end_date", "name")[:30]
    )
    stale_support = command_center.get("support_stale_rows", [])[:20]
    provisioning_breach_rows = command_center.get("provisioning_breach_rows", [])[:20]
    risk_rows = command_center.get("tenant_churn_risk_rows", [])[:20]
    platform_incidents = list(
        PlatformIncident.objects.select_related("affected_school")
        .filter(
            status__in=[
                PlatformIncident.Status.OPEN,
                PlatformIncident.Status.ACKNOWLEDGED,
                PlatformIncident.Status.MITIGATED,
            ]
        )
        .order_by("-detected_at", "-created_at")[:20]
    )
    incident_counts = {
        row["status"]: row["total"]
        for row in PlatformIncident.objects.values("status").annotate(total=Count("id"))
    }
    billing_watchlist = list(
        TenantSubscription.objects.select_related("school", "billing_account", "plan")
        .filter(
            status__in=[
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ]
        )
        .order_by("-updated_at", "school__name")[:20]
    )
    webhook_stack = legacy_webhook_sync_snapshot()
    platform_health = get_cached_platform_health()

    school_map = {
        school.id: school
        for school in School.objects.filter(
            id__in=[row["school_id"] for row in provisioning_breach_rows]
        ).only("id", "name", "slug")
    }
    for row in provisioning_breach_rows:
        row["school"] = school_map.get(row["school_id"])
    for row in risk_rows:
        school = row.get("school")
        if school is not None:
            row["admin_edit_url"] = ""

    operator_command_center_links = list(
        PlatformOperatorCommandCenterLink.objects.order_by("sort_order", "slug")
    )
    return render(
        request,
        "schools/super_command_center.html",
        {
            "command_center": command_center,
            "pending_schools": pending_schools,
            "trial_schools": trial_schools,
            "stale_support": stale_support,
            "provisioning_breach_rows": provisioning_breach_rows,
            "support_dashboard_url": reverse("super:support_dashboard"),
            "billing_dashboard_url": reverse("super:billing_dashboard"),
            "usage_url": reverse("super:usage"),
            "dashboard_url": reverse("super:dashboard"),
            "open_ticket_statuses": list(GlobalSupportTicket.Status.values),
            "risk_rows": risk_rows,
            "platform_incidents": platform_incidents,
            "incident_counts": incident_counts,
            "billing_watchlist": billing_watchlist,
            "webhook_stack": webhook_stack,
            "platform_health": platform_health,
            "platform_incidents_url": safe_platform_incidents_url(),
            "operator_command_center_links": operator_command_center_links,
        },
    )
