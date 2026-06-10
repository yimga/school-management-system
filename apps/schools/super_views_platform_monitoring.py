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

from .control_plane_lifecycle import batch_current_subscriptions, get_lifecycle_snapshot
from .fleet_status import format_fleet_summary_label, resolve_fleet_summary, resolve_school_fleet_status
from .models import School, TenantApiUsage, TenantQuotaLimit
from .super_dashboard_registry import (
    REGISTRY_PAGE_SIZE_OPTIONS,
    paginate_operator_schools,
)
from .super_views_constants import CONTROL_PLANE_METRIC_FAILURES
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_usage(request):
    """Plan I: Per-tenant API usage and quota limits for super-admin billing/health."""
    base_qs = (
        School.objects.filter(is_active=True)
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("name")
    )
    page, search, page_size, pagination_extra_query = paginate_operator_schools(
        request, base_qs, default_page_size=50
    )
    schools = list(page.object_list)
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
        {
            "schools": schools,
            "page_obj": page,
            "search_query": search,
            "page_size": page_size,
            "page_size_options": REGISTRY_PAGE_SIZE_OPTIONS,
            "pagination_extra_query": pagination_extra_query,
            "total_school_count": page.paginator.count,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_pulse(request):
    """S13: Global Pulse Map — HTML view for super dashboard link. Same data as API v1 super/pulse."""
    from apps.siteconfig.models import RevenueSnapshot

    active_qs = School.objects.filter(is_active=True)
    first_of_month = timezone.now().date().replace(day=1)
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        snapshots = RevenueSnapshot.objects.filter(
            snapshot_date=first_of_month
        ).aggregate(total=Sum("actual_revenue"), waived=Sum("waived_amount"))
        total_revenue = (snapshots["total"] or 0) + (snapshots["waived"] or 0)
    except DatabaseError:
        total_revenue = 0
    total_students = active_qs.aggregate(
        total=Count("student_profiles")
    )["total"] or 0
    active_school_count = active_qs.count()
    by_country = list(
        active_qs.values("default_region_id").annotate(
            school_count=Count("id"),
            student_count=Count("student_profiles", distinct=True),
        )
    )
    page, search, page_size, pagination_extra_query = paginate_operator_schools(
        request,
        active_qs.annotate(
            student_count=Count("student_profiles", distinct=True)
        ).order_by("name"),
        default_page_size=50,
    )
    tenants = list(page.object_list)
    return render(
        request,
        "schools/super_pulse.html",
        {
            "tenants": tenants,
            "page_obj": page,
            "search_query": search,
            "page_size": page_size,
            "page_size_options": REGISTRY_PAGE_SIZE_OPTIONS,
            "pagination_extra_query": pagination_extra_query,
            "total_students": total_students,
            "active_school_count": active_school_count,
            "total_revenue": total_revenue,
            "by_country": by_country,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_tenant_health(request):
    """S13: Tenant Health Monitor — HTML view for super dashboard link. Wedge 14–22: missing statutory for PUBLIC/GOVERNMENT_MINISTRY."""
    from apps.lifecycle.unified_lifecycle import resolve_unified_lifecycle
    from apps.platform_runtime.models import PlatformOperatorTenantHealthLink
    from apps.policies.resolver import get_effective_policy

    base_qs = School.objects.all().annotate(
        student_count=Count("student_profiles", distinct=True)
    ).order_by("name")
    page, search, page_size, pagination_extra_query = paginate_operator_schools(
        request, base_qs, default_page_size=50
    )
    tenants = list(page.object_list)
    subs = batch_current_subscriptions(tenants)
    fleet_summary = resolve_fleet_summary()
    for school in tenants:
        school.lifecycle = get_lifecycle_snapshot(
            school, cached_subscription=subs.get(school.pk)
        )
        school.fleet_status = resolve_school_fleet_status(
            school, cached_subscription=subs.get(school.pk)
        )
        school.unified_lifecycle = resolve_unified_lifecycle(school)
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
            "tenants": tenants,
            "page_obj": page,
            "search_query": search,
            "page_size": page_size,
            "page_size_options": REGISTRY_PAGE_SIZE_OPTIONS,
            "pagination_extra_query": pagination_extra_query,
            "total_tenant_count": page.paginator.count,
            "fleet_summary_label": format_fleet_summary_label(fleet_summary),
            "fleet_summary": fleet_summary,
            "operator_tenant_health_links": operator_tenant_health_links,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_fleet_wall(request):
    """Full-fleet operator wall — all schools as live tiles with chunked SSE bootstrap."""
    from apps.schools.fleet_wall_payload import (
        FLEET_WALL_DEFAULT_CHUNK_SIZE,
        build_fleet_wall_context,
        build_fleet_wall_rows,
        parse_fleet_wall_query,
    )

    chunk_size, search = parse_fleet_wall_query(request)
    ctx = build_fleet_wall_context(q=search)
    initial_tiles = build_fleet_wall_rows(search)[:chunk_size]
    return render(
        request,
        "schools/super_fleet_wall.html",
        {
            "search_query": search,
            "wall_chunk_size": chunk_size or FLEET_WALL_DEFAULT_CHUNK_SIZE,
            "fleet_summary_label": ctx["summary_label"],
            "fleet_summary": ctx["summary"],
            "total_school_count": ctx["total"],
            "initial_tiles": initial_tiles,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
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

    from apps.lifecycle.enrollment_workflow_matrix import (
        build_enrollment_track,
        build_registration_track,
    )
    from apps.lifecycle.unified_lifecycle import (
        build_offboarding_checklist,
        resolve_unified_lifecycle,
    )
    from apps.schools.tenant_offboarding import get_offboarding_snapshot

    offboarding = get_offboarding_snapshot(school)
    offboarding_checklist = build_offboarding_checklist(school)
    unified_lifecycle = resolve_unified_lifecycle(school)
    lifecycle_registration = build_registration_track(school)
    lifecycle_enrollment = build_enrollment_track(school)
    try:
        from apps.schools.provisioning_progress import resolve_provisioning_progress

        provisioning_progress = resolve_provisioning_progress(school)
    except ImportError:
        provisioning_progress = {}
    return render(
        request,
        "schools/super_tenant_360.html",
        {
            "school": school,
            "provisioning_progress": provisioning_progress,
            "lifecycle": get_lifecycle_snapshot(school),
            "identity": identity,
            "blueprint_code": blueprint_code,
            "policy_summary": policy_summary,
            "runtime_trace": trace,
            "runtime_warnings": warnings,
            "dashboard_url": reverse("super:dashboard"),
            "offboarding": offboarding,
            "offboarding_checklist": offboarding_checklist,
            "unified_lifecycle": unified_lifecycle,
            "lifecycle_registration": lifecycle_registration,
            "lifecycle_enrollment": lifecycle_enrollment,
            "api_offboarding_url": reverse(
                "super:api_school_offboarding", args=[school.id]
            ),
            "api_offboarding_export_url": reverse(
                "super:api_school_offboarding_export", args=[school.id]
            ),
            "api_offboarding_deactivate_url": reverse(
                "super:api_school_offboarding_deactivate", args=[school.id]
            ),
            "api_offboarding_hold_url": reverse(
                "super:api_school_offboarding_hold", args=[school.id]
            ),
            "api_offboarding_purge_url": reverse(
                "super:api_school_offboarding_purge", args=[school.id]
            ),
            "api_offboarding_schedule_url": reverse(
                "super:api_school_offboarding_schedule", args=[school.id]
            ),
            "api_offboarding_dual_approve_url": reverse(
                "super:api_school_offboarding_dual_approve", args=[school.id]
            ),
            "api_offboarding_export_download_url": reverse(
                "super:api_school_offboarding_export_download", args=[school.id]
            ),
            "offboarding_queue_url": reverse("super:offboarding_queue"),
            "api_school_timeline_url": reverse(
                "super:api_school_timeline", args=[school.id]
            ),
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
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
