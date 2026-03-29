"""
Platform monitoring: usage, pulse, tenant health, tenant 360, control health hub (BR-12 split from super_views).
"""

from __future__ import annotations

from django.db import DatabaseError
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.tenancy.context import TenantContext

from .control_plane_lifecycle import get_lifecycle_snapshot
from .models import School, TenantApiUsage, TenantQuotaLimit
from .super_views_constants import CONTROL_PLANE_METRIC_FAILURES


def super_usage(request):
    """Plan I: Per-tenant API usage and quota limits for super-admin billing/health."""
    schools = list(
        School.objects.filter(is_active=True)
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("name")
    )
    school_ids = [s.pk for s in schools]
    usage_agg = {
        (r["school_id"], r["limit_type"]): r["total"]
        for r in TenantApiUsage.objects.filter(school_id__in=school_ids)
        .values("school_id", "limit_type")
        .annotate(total=Sum("request_count"))
    }
    quotas = {}
    for q in TenantQuotaLimit.objects.filter(
        school_id__in=school_ids, is_active=True
    ).values("school_id", "limit_type", "limit_value", "period_days"):
        quotas.setdefault(q["school_id"], []).append(q)
    for school in schools:
        school.api_usage = {
            k: v for (sid, k), v in usage_agg.items() if sid == school.pk
        }
        school.quota_limits_list = quotas.get(school.pk, [])
    return render(
        request,
        "schools/super_usage.html",
        {"schools": schools},
    )


def super_pulse(request):
    """S13: Global Pulse Map — HTML view for super dashboard link. Same data as API v1 super/pulse."""
    from apps.siteconfig.models import RevenueSnapshot

    schools = list(
        School.objects.filter(is_active=True)
        .annotate(student_count=Count("student_profiles", distinct=True))
        .values(
            "id",
            "name",
            "slug",
            "subdomain",
            "default_region_id",
            "student_count",
            "last_activity",
        )
    )
    first_of_month = timezone.now().date().replace(day=1)
    try:
        snapshots = RevenueSnapshot.objects.filter(
            snapshot_date=first_of_month
        ).aggregate(total=Sum("actual_revenue"), waived=Sum("waived_amount"))
        total_revenue = (snapshots["total"] or 0) + (snapshots["waived"] or 0)
    except DatabaseError:
        total_revenue = 0
    total_students = sum(s["student_count"] for s in schools)
    by_country = list(
        School.objects.filter(is_active=True)
        .values("default_region_id")
        .annotate(
            school_count=Count("id"),
            student_count=Count("student_profiles", distinct=True),
        )
    )
    return render(
        request,
        "schools/super_pulse.html",
        {
            "tenants": schools,
            "total_students": total_students,
            "total_revenue": total_revenue,
            "by_country": by_country,
        },
    )


def super_tenant_health(request):
    """S13: Tenant Health Monitor — HTML view for super dashboard link. Wedge 14–22: missing statutory for PUBLIC/GOVERNMENT_MINISTRY."""
    from apps.platform_runtime.models import PlatformOperatorTenantHealthLink
    from apps.policies.resolver import get_effective_policy

    schools = list(
        School.objects.all()
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("name")
    )
    for school in schools:
        school.lifecycle = get_lifecycle_snapshot(school)
        sector = (getattr(school, "primary_sector", None) or "").strip().upper()
        if sector in ("PUBLIC", "GOVERNMENT_MINISTRY"):
            policy = get_effective_policy(school)
            compliance = policy.get("compliance") or {}
            school.missing_statutory = compliance.get("statutory_enabled") is not True
        else:
            school.missing_statutory = False
    operator_tenant_health_links = list(
        PlatformOperatorTenantHealthLink.objects.order_by("sort_order", "slug")
    )
    return render(
        request,
        "schools/super_tenant_health.html",
        {
            "tenants": schools,
            "operator_tenant_health_links": operator_tenant_health_links,
        },
    )


def super_tenant_360(request, school_id):
    """Phase 9: Tenant 360 — identity, domain, blueprint, policy, plan, workflow/dashboard packs, runtime inspector."""
    from apps.platform_runtime.runtime_resolver import build_tenant_runtime

    school = get_object_or_404(School, id=school_id)
    tenant_ctx = TenantContext(
        tenant_id=str(getattr(school, "id", "") or ""),
        schema_name=getattr(school, "schema_name", None),
        school_id=getattr(school, "id", None),
        country=getattr(school, "country", None),
        timezone=getattr(school, "timezone", None),
        feature_flags={},
        policy_overrides={},
        host=request.get_host() if request else "",
    )
    try:
        runtime = build_tenant_runtime(tenant_ctx, request=None, school=school)
    except CONTROL_PLANE_METRIC_FAILURES:
        runtime = None

    identity = None
    blueprint_code = None
    policy_summary = {}
    trace = []
    warnings = []
    if runtime:
        identity = {
            "id": getattr(getattr(runtime, "tenant", None), "id", None),
            "slug": getattr(getattr(runtime, "tenant", None), "slug", None),
            "schema_name": getattr(
                getattr(runtime, "tenant", None), "schema_name", None
            ),
        }
        bp = getattr(runtime, "blueprint", None)
        blueprint_code = getattr(bp, "code", None) or getattr(bp, "family", None)
        if getattr(runtime, "policy_typed", None):
            pt = runtime.policy_typed
            policy_summary = {
                "admissions": bool(getattr(pt, "admissions", None)),
                "finance": bool(getattr(pt, "finance", None)),
                "gradebook": bool(getattr(pt, "gradebook", None)),
            }
        debug = getattr(runtime, "debug", None)
        if debug:
            trace = getattr(debug, "compilation_trace", []) or []
            warnings = getattr(debug, "warnings", []) or []

    return render(
        request,
        "schools/super_tenant_360.html",
        {
            "school": school,
            "lifecycle": get_lifecycle_snapshot(school),
            "identity": identity,
            "blueprint_code": blueprint_code,
            "policy_summary": policy_summary,
            "runtime_trace": trace,
            "runtime_warnings": warnings,
            "dashboard_url": reverse("super:dashboard"),
        },
    )


def super_control_health_dashboard(request):
    """
    Control plane health hub: single entry for runbooks, SLOs, incidents, tenant health.
    Linked from super dashboard (north-star: one place for ops health).
    """
    from django.conf import settings

    links = []
    try:
        links.append(
            {
                "label": "Tenant health",
                "url": reverse("super:tenant_health"),
                "description": "Per-tenant roster and activity",
            }
        )
    except NoReverseMatch:
        pass
    try:
        url = reverse("platform_incidents_console")
        links.append(
            {
                "label": "Incident console",
                "url": url,
                "description": "Platform incidents and status",
            }
        )
    except NoReverseMatch:
        pass
    try:
        url = reverse("api_operational_slo_dashboard") + "?format=html"
        links.append(
            {
                "label": "SLO dashboard",
                "url": url,
                "description": "Operational SLO metrics (webhook & sync)",
            }
        )
    except NoReverseMatch:
        pass
    runbooks_url = getattr(settings, "CONTROL_PLANE_RUNBOOKS_URL", None) or ""
    if runbooks_url:
        links.append(
            {
                "label": "Runbooks",
                "url": runbooks_url,
                "description": "Operational runbooks and playbooks",
            }
        )
    return render(
        request,
        "schools/super_control_health.html",
        {"links": links, "dashboard_url": reverse("super:dashboard")},
    )
