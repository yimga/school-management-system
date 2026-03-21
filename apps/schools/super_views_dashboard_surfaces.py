"""
Super dashboard v1/v2 and layout API (BR-12 split from super_views).
"""

from __future__ import annotations

import json

from django.db import DatabaseError
from django.db.models import Count, OuterRef, Subquery, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.registries.models import (
    CountryRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    SubdivisionRegistry,
)
from .decision_architecture import get_decision_architecture_for_page
from .models import School, SchoolProvisioningEvent
from .super_views_command_center_data import build_command_center_data as _build_command_center_data
from .super_views_constants import CONTROL_PLANE_METRIC_FAILURES
from .super_views_dashboard_helpers import (
    brand_profile_for_school,
    education_level_label,
    education_system_type_label,
    get_super_dashboard_section_order,
    month_options as build_month_options_list,
    parse_month_param,
    safe_command_center_url,
    safe_percentage,
    safe_registry_url,
    selected_system_names,
    status_tone,
)
from .super_views_helpers import (
    safe_platform_incidents_url,
    safe_school_timeline_url,
)

def super_dashboard(request):
    """List all schools with basic stats. Phase E: Financial Bento. Phase H: Registry link, selected education systems."""
    from django.db.models import Sum
    from apps.siteconfig.models import RevenueSnapshot

    # Global date filter: ?month=YYYY-MM for Financial Mission Control
    first_of_month = parse_month_param(request)
    month_options = build_month_options_list(12)
    current_request_month = first_of_month.strftime("%Y-%m")

    latest_event_query = SchoolProvisioningEvent.objects.filter(
        school_id=OuterRef("pk")
    ).order_by("-created_at", "-id")
    schools = list(
        School.objects.all()
        .prefetch_related("tenant_systems__system")
        .order_by("name")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
        .annotate(
            latest_event_type=Subquery(latest_event_query.values("event_type")[:1])
        )
        .annotate(latest_event_status=Subquery(latest_event_query.values("status")[:1]))
        .annotate(
            latest_event_created_at=Subquery(
                latest_event_query.values("created_at")[:1]
            )
        )
    )
    for school in schools:
        school.timeline_url = safe_school_timeline_url(school.pk)
        school.sync_repair_url = reverse("super:sync_repair", args=[school.pk])
        school.selected_systems = selected_system_names(school)

    # Phase E: Financial Mission Control / Bento (selected month); resilient if RevenueSnapshot not migrated
    total_mrr = total_waived = waiver_percentage = 0
    revenue_by_country = []
    billing_model_breakdown = []
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        agg = snapshots.aggregate(
            total_actual=Sum("actual_revenue"), total_waived=Sum("waived_amount")
        )
        total_mrr = agg["total_actual"] or 0
        total_waived = agg["total_waived"] or 0
        total_all = total_mrr + total_waived
        waiver_percentage = (
            (float(total_waived) / float(total_all) * 100) if total_all else 0
        )
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")[:20]
        )
        billing_model_breakdown = list(
            snapshots.values("billing_model")
            .annotate(
                count=Count("id"),
                actual=Sum("actual_revenue"),
                waived=Sum("waived_amount"),
            )
            .order_by("-actual", "-waived")
        )
    except DatabaseError:
        pass

    # Phase H optional: approval workflow — count and list pending schools
    pending_schools = list(
        School.objects.filter(is_approved=False)
        .prefetch_related("tenant_systems__system")
        .order_by("-created_at")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
    )
    for school in pending_schools:
        school.timeline_url = safe_school_timeline_url(school.pk)
        school.selected_systems = selected_system_names(school)
    pending_approval_count = len(pending_schools)

    # Section 8.7–8.8: Health / resource hogs (PostgreSQL table sizes)
    health_top_tables = []
    health_schema_stats = []
    try:
        from .health_utils import get_top_tables_by_size, get_global_health_stats

        health_top_tables = get_top_tables_by_size(limit=10)
        health_schema_stats = get_global_health_stats()
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    command_center = _build_command_center_data()

    # North Star: prefer Total MRR when present, else school count
    school_count = len(schools)
    if total_mrr is not None and total_mrr > 0:
        north_star_value = total_mrr
        north_star_label = "Total MRR"
        north_star_formatted = f"${total_mrr:,.2f}"
    else:
        north_star_value = school_count
        north_star_label = "Schools"
        north_star_formatted = str(school_count)

    # Next-best-action strip (pending approvals, trials ending soon)
    next_best_actions = []
    if pending_approval_count:
        next_best_actions.append(
            {
                "label": f"{pending_approval_count} pending approval"
                + ("s" if pending_approval_count != 1 else ""),
                "url": request.path + "#pending-approval",
                "count": pending_approval_count,
            }
        )
    if command_center.get("trial_ending_soon_count", 0):
        cc_url = safe_command_center_url()
        if cc_url:
            next_best_actions.append(
                {
                    "label": f"{command_center['trial_ending_soon_count']} trial(s) ending soon",
                    "url": cc_url,
                    "count": command_center["trial_ending_soon_count"],
                }
            )
    if command_center.get("provisioning_sla_breaches", 0):
        cc_url = safe_command_center_url()
        if cc_url:
            next_best_actions.append(
                {
                    "label": f"{command_center['provisioning_sla_breaches']} provisioning breach(es)",
                    "url": cc_url,
                    "count": command_center["provisioning_sla_breaches"],
                }
            )

    return render(
        request,
        "schools/super_dashboard.html",
        {
            "schools": schools,
            "pending_schools": pending_schools,
            "pending_approval_count": pending_approval_count,
            "total_mrr": total_mrr,
            "total_waived": total_waived,
            "waiver_percentage": round(waiver_percentage, 1),
            "revenue_by_country": revenue_by_country,
            "billing_model_breakdown": billing_model_breakdown,
            "revenue_snapshot_month": first_of_month,
            "current_request_month": current_request_month,
            "month_options": month_options,
            "school_count": school_count,
            "north_star_value": north_star_value,
            "north_star_label": north_star_label,
            "north_star_formatted": north_star_formatted,
            "next_best_actions": next_best_actions,
            "registry_url": safe_registry_url(),
            "command_center_url": safe_command_center_url(),
            "health_top_tables": health_top_tables,
            "health_schema_stats": health_schema_stats,
            "command_center": command_center,
        },
    )

def api_super_dashboard_layout(request):
    """GET: return section_order for current user. POST/PUT/PATCH: save section_order (JSON body)."""
    from apps.runtime_blueprints.models import (
        SuperAdminDashboardPreference,
        SUPER_DASHBOARD_DEFAULT_SECTION_ORDER,
    )

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.method == "GET":
        order = get_super_dashboard_section_order(request.user)
        return JsonResponse({"section_order": order})
    # POST/PUT/PATCH: save
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    order = body.get("section_order")
    if not isinstance(order, list):
        return JsonResponse({"error": "section_order must be a list"}, status=400)
    valid_ids = set(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
    order = [str(s) for s in order if s in valid_ids]
    pref, _ = SuperAdminDashboardPreference.objects.get_or_create(
        user=request.user,
        defaults={
            "section_order": order or list(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
        },
    )
    pref.section_order = order or list(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
    pref.save(update_fields=["section_order", "updated_at"])
    return JsonResponse({"section_order": pref.get_section_order()})

def super_dashboard_v2(request):
    """Mission-control control plane for the manager host."""
    from apps.billing.models import BillingAccount, TenantSubscription
    from apps.events.legacy_bridge import legacy_webhook_sync_snapshot
    from apps.observability.models import PlatformIncident
    from apps.observability.monitoring import SystemHealthMonitor
    from apps.brand_experience.models import BrandProfile
    from apps.siteconfig.models import RevenueSnapshot

    first_of_month = parse_month_param(request)
    month_options = build_month_options_list(12)
    current_request_month = first_of_month.strftime("%Y-%m")

    latest_event_query = SchoolProvisioningEvent.objects.filter(
        school_id=OuterRef("pk")
    ).order_by("-created_at", "-id")
    latest_subscription_query = TenantSubscription.objects.filter(
        school_id=OuterRef("pk")
    ).order_by("-updated_at", "-created_at")
    country_names = {
        code: name
        for code, name in CountryRegistry.objects.filter(is_active=True).values_list(
            "code", "name"
        )
    }
    schools = list(
        School.objects.all()
        .select_related("subdivision", "default_region")
        .prefetch_related(
            "tenant_systems__system", "education_levels", "education_system_types"
        )
        .order_by("-is_active", "name")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
        .annotate(
            latest_event_type=Subquery(latest_event_query.values("event_type")[:1])
        )
        .annotate(latest_event_status=Subquery(latest_event_query.values("status")[:1]))
        .annotate(
            latest_event_created_at=Subquery(
                latest_event_query.values("created_at")[:1]
            )
        )
        .annotate(
            latest_subscription_status=Subquery(
                latest_subscription_query.values("status")[:1]
            )
        )
        .annotate(
            latest_subscription_amount=Subquery(
                latest_subscription_query.values("billed_amount")[:1]
            )
        )
        .annotate(
            latest_subscription_period_end=Subquery(
                latest_subscription_query.values("current_period_end")[:1]
            )
        )
    )

    total_mrr = total_waived = waiver_percentage = 0
    revenue_by_country = []
    billing_model_breakdown = []
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        agg = snapshots.aggregate(
            total_actual=Sum("actual_revenue"), total_waived=Sum("waived_amount")
        )
        total_mrr = agg["total_actual"] or 0
        total_waived = agg["total_waived"] or 0
        total_all = total_mrr + total_waived
        waiver_percentage = (
            (float(total_waived) / float(total_all) * 100) if total_all else 0
        )
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")[:20]
        )
        billing_model_breakdown = list(
            snapshots.values("billing_model")
            .annotate(
                count=Count("id"),
                actual=Sum("actual_revenue"),
                waived=Sum("waived_amount"),
            )
            .order_by("-actual", "-waived")
        )
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    pending_schools = list(
        School.objects.filter(is_approved=False)
        .prefetch_related("tenant_systems__system")
        .order_by("-created_at")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
    )
    for school in pending_schools:
        school.timeline_url = safe_school_timeline_url(school.pk)
        school.selected_systems = selected_system_names(school)
        school.country_display = country_names.get(
            school.canonical_country_code, school.canonical_country_code or "Unassigned"
        )
    pending_approval_count = len(pending_schools)

    health_top_tables = []
    health_schema_stats = []
    try:
        from .health_utils import get_top_tables_by_size, get_global_health_stats

        health_top_tables = get_top_tables_by_size(limit=10)
        health_schema_stats = get_global_health_stats()
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    command_center = _build_command_center_data()
    platform_incidents = list(
        PlatformIncident.objects.select_related("affected_school")
        .filter(
            status__in=[
                PlatformIncident.Status.OPEN,
                PlatformIncident.Status.ACKNOWLEDGED,
                PlatformIncident.Status.MITIGATED,
            ]
        )
        .order_by("-detected_at", "-created_at")[:12]
    )
    incident_counts = {
        row["status"]: row["total"]
        for row in PlatformIncident.objects.values("status").annotate(total=Count("id"))
    }
    critical_incident_count = PlatformIncident.objects.filter(
        status__in=[
            PlatformIncident.Status.OPEN,
            PlatformIncident.Status.ACKNOWLEDGED,
            PlatformIncident.Status.MITIGATED,
        ],
        severity__in=[
            PlatformIncident.Severity.CRITICAL,
            PlatformIncident.Severity.HIGH,
        ],
    ).count()
    billing_watchlist = list(
        TenantSubscription.objects.select_related("school", "billing_account", "plan")
        .filter(
            status__in=[
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ]
        )
        .order_by("-updated_at", "school__name")[:12]
    )
    active_subscription_count = TenantSubscription.objects.filter(
        status__in=[
            TenantSubscription.Status.ACTIVE,
            TenantSubscription.Status.TRIALING,
        ]
    ).count()
    billing_account_count = BillingAccount.objects.count()
    webhook_stack = legacy_webhook_sync_snapshot()
    try:
        platform_health = SystemHealthMonitor.get_comprehensive_health()
    except CONTROL_PLANE_METRIC_FAILURES:
        platform_health = {
            "overall_status": "warning",
            "cpu": {"usage_percent": 0.0, "threshold": 80.0, "status": "warning"},
            "memory": {
                "usage_percent": 0.0,
                "used_mb": 0.0,
                "threshold": 85.0,
                "status": "warning",
            },
            "disk": {
                "usage_percent": 0.0,
                "free_gb": 0.0,
                "threshold": 90.0,
                "status": "warning",
            },
            "database": {"status": "unhealthy", "response_time_ms": 0.0},
            "cache": {"status": "unhealthy", "type": "unknown"},
        }

    registry_counts = {
        "countries": CountryRegistry.objects.filter(is_active=True).count(),
        "subdivisions": SubdivisionRegistry.objects.filter(is_active=True).count(),
        "education_levels": EducationLevelRegistry.objects.filter(
            is_active=True
        ).count(),
        "education_system_types": EducationSystemTypeRegistry.objects.filter(
            is_active=True
        ).count(),
    }
    brand_profile_ids = set(BrandProfile.objects.values_list("school_id", flat=True))
    churn_risk_lookup = {
        str(row["school"].id): row
        for row in command_center.get("tenant_churn_risk_rows", [])
        if row.get("school") is not None
    }
    incident_school_ids = {
        incident.affected_school_id
        for incident in platform_incidents
        if getattr(incident, "affected_school_id", None)
    }
    countries_live_codes = {
        school.canonical_country_code
        for school in schools
        if school.canonical_country_code
    }
    countries_live_count = len(countries_live_codes)
    identity_complete_count = 0
    brand_profile_count = 0
    verified_domain_count = 0
    custom_domain_count = 0
    impersonation_ready_count = 0
    attention_school_count = 0
    recent_schools = sorted(
        schools, key=lambda school: (school.created_at, school.name), reverse=True
    )[:8]

    for school in schools:
        school.timeline_url = safe_school_timeline_url(school.pk)
        school.sync_repair_url = reverse("super:sync_repair", args=[school.pk])
        school.selected_systems = selected_system_names(school)
        school.country_display = country_names.get(
            school.canonical_country_code, school.canonical_country_code or "Unassigned"
        )
        school.subdivision_display = (
            school.subdivision.name if school.subdivision_id else "-"
        )
        school.education_level_labels = [
            education_level_label(level, school.canonical_country_code)
            for level in school.education_levels.all()
        ]
        school.education_system_type_labels = [
            education_system_type_label(system_type, school.canonical_country_code)
            for system_type in school.education_system_types.all()
        ]
        school.has_brand_profile = (
            school.id in brand_profile_ids
            or brand_profile_for_school(school) is not None
        )
        school.brand_status = (
            "BrandProfile" if school.has_brand_profile else "Legacy fallback"
        )
        school.subscription_status = (
            school.latest_subscription_status or "UNSEEDED"
        ).upper()
        school.subscription_tone = status_tone(school.subscription_status)
        school.identity_status = "missing"
        if (
            school.canonical_country_code
            or school.education_level_labels
            or school.education_system_type_labels
        ):
            school.identity_status = "partial"
        if (
            school.canonical_country_code
            and school.education_level_labels
            and school.education_system_type_labels
        ):
            school.identity_status = "complete"
        school.identity_tone = status_tone(
            "success" if school.identity_status == "complete" else "warning"
        )
        school.attention_reasons = []
        if not school.is_approved:
            school.attention_reasons.append("Pending approval")
        if (
            getattr(school, "latest_event_status", "")
            == SchoolProvisioningEvent.Status.ERROR
        ):
            school.attention_reasons.append("Provisioning error")
        if school.subscription_status in {
            TenantSubscription.Status.PAST_DUE,
            TenantSubscription.Status.SUSPENDED,
        }:
            school.attention_reasons.append(
                f"Billing {school.subscription_status.lower().replace('_', ' ')}"
            )
        risk_row = churn_risk_lookup.get(str(school.pk))
        if risk_row and risk_row.get("reasons"):
            school.attention_reasons.append(risk_row["reasons"][0])
        if school.pk in incident_school_ids:
            school.attention_reasons.append("Open platform incident")
        if school.identity_status != "complete":
            school.attention_reasons.append("Canonical identity incomplete")
        school.attention_reasons = school.attention_reasons[:4]
        if school.attention_reasons:
            attention_school_count += 1
        school.roster_state = "healthy"
        if not school.is_active:
            school.roster_state = "inactive"
        elif not school.is_approved:
            school.roster_state = "pending"
        elif school.attention_reasons:
            school.roster_state = "attention"
        school.roster_search = " ".join(
            filter(
                None,
                [
                    school.name,
                    school.slug,
                    school.subdomain,
                    school.country_display,
                    school.subdivision_display,
                    " ".join(school.education_level_labels),
                    " ".join(school.education_system_type_labels),
                    " ".join(school.selected_systems),
                    " ".join(school.attention_reasons),
                    school.subscription_status,
                ],
            )
        ).lower()
        if school.identity_status == "complete":
            identity_complete_count += 1
        if school.has_brand_profile:
            brand_profile_count += 1
        if school.custom_domain:
            custom_domain_count += 1
        if school.custom_domain_verified:
            verified_domain_count += 1
        if school.impersonation_consent_granted_at:
            impersonation_ready_count += 1

    schools.sort(
        key=lambda school: (-len(school.attention_reasons), school.name.lower())
    )

    country_rollup = list(
        School.objects.exclude(country_code="")
        .values("country_code")
        .annotate(
            school_count=Count("id"),
            student_count=Count("student_profiles", distinct=True),
        )
        .order_by("-school_count", "country_code")[:12]
    )
    revenue_by_country_lookup = {
        str(row.get("country_code") or "").upper(): row for row in revenue_by_country
    }
    for row in country_rollup:
        country_code = str(row.get("country_code") or "").upper()
        revenue_row = revenue_by_country_lookup.get(country_code, {})
        row["country_name"] = country_names.get(
            country_code, country_code or "Unassigned"
        )
        row["actual_revenue"] = revenue_row.get("actual") or 0
        row["waived_revenue"] = revenue_row.get("waived") or 0

    school_count = len(schools)
    if total_mrr is not None and total_mrr > 0:
        north_star_label = "Total MRR"
        north_star_formatted = f"${total_mrr:,.2f}"
    else:
        north_star_label = "Schools"
        north_star_formatted = str(school_count)

    next_best_actions = []
    if pending_approval_count:
        next_best_actions.append(
            {
                "label": f"{pending_approval_count} pending approval"
                + ("s" if pending_approval_count != 1 else ""),
                "url": request.path + "#cp-action-queue",
                "count": pending_approval_count,
            }
        )
    if command_center.get("trial_ending_soon_count", 0):
        cc_url = safe_command_center_url()
        if cc_url:
            next_best_actions.append(
                {
                    "label": f"{command_center['trial_ending_soon_count']} trial(s) ending soon",
                    "url": cc_url,
                    "count": command_center["trial_ending_soon_count"],
                }
            )
    if command_center.get("provisioning_sla_breaches", 0):
        cc_url = safe_command_center_url()
        if cc_url:
            next_best_actions.append(
                {
                    "label": f"{command_center['provisioning_sla_breaches']} provisioning breach(es)",
                    "url": cc_url,
                    "count": command_center["provisioning_sla_breaches"],
                }
            )
    if platform_incidents:
        next_best_actions.append(
            {
                "label": f"{len(platform_incidents)} live incident(s)",
                "url": safe_platform_incidents_url() or request.path,
                "count": len(platform_incidents),
            }
        )

    overview_cards = [
        {
            "label": "Fleet tenants",
            "value": school_count,
            "meta": f"{sum(1 for school in schools if school.is_active)} active / {pending_approval_count} pending approval",
            "tone": "blue",
        },
        {
            "label": north_star_label,
            "value": north_star_formatted,
            "meta": f"${total_waived:,.2f} waived in {first_of_month.strftime('%b %Y')}",
            "tone": "emerald",
        },
        {
            "label": "Open platform incidents",
            "value": len(platform_incidents),
            "meta": f"{critical_incident_count} critical or high severity",
            "tone": "crimson" if platform_incidents else "slate",
        },
        {
            "label": "Support backlog 48h+",
            "value": command_center.get("support_backlog_48h_count", 0),
            "meta": f"{command_center.get('support_backlog_7d_count', 0)} older than 7 days",
            "tone": "amber"
            if command_center.get("support_backlog_48h_count", 0)
            else "slate",
        },
        {
            "label": "Countries live",
            "value": countries_live_count,
            "meta": f"{registry_counts['countries']} countries in registry / {registry_counts['subdivisions']} subdivisions",
            "tone": "sky",
        },
        {
            "label": "Billing exceptions",
            "value": len(billing_watchlist),
            "meta": f"{active_subscription_count} active or trialing subscriptions / {billing_account_count} billing accounts",
            "tone": "violet" if billing_watchlist else "slate",
        },
    ]
    workstream_cards = [
        {
            "title": "Mission queues",
            "metric": pending_approval_count
            + command_center.get("support_backlog_48h_count", 0)
            + len(platform_incidents),
            "meta": "Approvals, stale support, incidents, and provisioning breaches",
            "url": safe_command_center_url(),
            "cta": "Open queues",
        },
        {
            "title": "Platform billing",
            "metric": active_subscription_count,
            "meta": f"{len(billing_watchlist)} tenants need billing attention",
            "url": reverse("super:billing_dashboard"),
            "cta": "Inspect billing",
        },
        {
            "title": "Incident console",
            "metric": len(platform_incidents),
            "meta": f"{critical_incident_count} critical/high severity incidents",
            "url": safe_platform_incidents_url(),
            "cta": "Review incidents",
        },
        {
            "title": "Usage and quotas",
            "metric": command_center.get("tenant_churn_risk_count", 0),
            "meta": "Usage posture, risk watchlist, and adoption signals",
            "url": reverse("super:usage"),
            "cta": "View usage",
        },
        {
            "title": "Fleet health",
            "metric": str(platform_health.get("overall_status", "unknown")).upper(),
            "meta": f"Webhook drift groups: {webhook_stack.get('unsynced_legacy_groups', 0)}",
            "url": reverse("super:tenant_health"),
            "cta": "Audit tenants",
        },
        {
            "title": "Health hub",
            "metric": "—",
            "meta": "Runbooks, SLOs, incidents, tenant health",
            "url": reverse("super:control_health"),
            "cta": "Health hub",
        },
        {
            "title": "Tenant Studio",
            "metric": registry_counts["education_system_types"],
            "meta": "Registry-backed onboarding with branding and control-plane defaults",
            "url": reverse("super:create_school_wizard"),
            "cta": "Open tenant studio",
        },
    ]
    readiness_cards = [
        {
            "label": "Canonical identity",
            "value": f"{identity_complete_count}/{school_count}",
            "meta": f"{school_count - identity_complete_count} tenants still partial or missing",
            "tone": "success" if identity_complete_count == school_count else "warning",
        },
        {
            "label": "BrandProfile coverage",
            "value": f"{brand_profile_count}/{school_count}",
            "meta": f"{school_count - brand_profile_count} tenants still rely on compatibility fallbacks",
            "tone": "success" if brand_profile_count == school_count else "warning",
        },
        {
            "label": "Verified domains",
            "value": f"{verified_domain_count}/{custom_domain_count or 0}",
            "meta": f"{custom_domain_count} custom domains configured",
            "tone": "success"
            if custom_domain_count and verified_domain_count == custom_domain_count
            else "neutral",
        },
        {
            "label": "Support impersonation consent",
            "value": f"{impersonation_ready_count}/{school_count}",
            "meta": "JIT consent grants available for audited support access",
            "tone": "neutral",
        },
    ]
    platform_health_cards = [
        {
            "label": "CPU",
            "value": f"{platform_health.get('cpu', {}).get('usage_percent', 0):.1f}%",
            "meta": f"threshold {platform_health.get('cpu', {}).get('threshold', 0)}%",
            "tone": status_tone(platform_health.get("cpu", {}).get("status", "")),
        },
        {
            "label": "Memory",
            "value": f"{platform_health.get('memory', {}).get('usage_percent', 0):.1f}%",
            "meta": f"{platform_health.get('memory', {}).get('used_mb', 0):.0f} MB used",
            "tone": status_tone(platform_health.get("memory", {}).get("status", "")),
        },
        {
            "label": "Disk",
            "value": f"{platform_health.get('disk', {}).get('usage_percent', 0):.1f}%",
            "meta": f"{platform_health.get('disk', {}).get('free_gb', 0):.1f} GB free",
            "tone": status_tone(platform_health.get("disk", {}).get("status", "")),
        },
        {
            "label": "Database",
            "value": str(
                platform_health.get("database", {}).get("status", "unknown")
            ).upper(),
            "meta": f"{platform_health.get('database', {}).get('response_time_ms', 0):.1f} ms health check",
            "tone": status_tone(platform_health.get("database", {}).get("status", "")),
        },
    ]

    return render(
        request,
        "schools/super_dashboard.html",
        {
            "schools": schools,
            "pending_schools": pending_schools,
            "pending_approval_count": pending_approval_count,
            "total_mrr": total_mrr,
            "total_waived": total_waived,
            "waiver_percentage": round(waiver_percentage, 1),
            "revenue_by_country": revenue_by_country,
            "billing_model_breakdown": billing_model_breakdown,
            "revenue_snapshot_month": first_of_month,
            "current_request_month": current_request_month,
            "month_options": month_options,
            "school_count": school_count,
            "north_star_label": north_star_label,
            "north_star_formatted": north_star_formatted,
            "next_best_actions": next_best_actions,
            "registry_url": safe_registry_url(),
            "command_center_url": safe_command_center_url(),
            "health_top_tables": health_top_tables,
            "health_schema_stats": health_schema_stats,
            "command_center": command_center,
            "platform_health": platform_health,
            "platform_health_cards": platform_health_cards,
            "platform_incidents": platform_incidents,
            "platform_incidents_url": safe_platform_incidents_url(),
            "incident_counts": incident_counts,
            "critical_incident_count": critical_incident_count,
            "billing_watchlist": billing_watchlist,
            "webhook_stack": webhook_stack,
            "registry_counts": registry_counts,
            "country_rollup": country_rollup,
            "countries_live_count": countries_live_count,
            "countries_live_pct": safe_percentage(
                countries_live_count, registry_counts["countries"]
            ),
            "overview_cards": overview_cards,
            "workstream_cards": workstream_cards,
            "readiness_cards": readiness_cards,
            "attention_school_count": attention_school_count,
            "recent_schools": recent_schools,
            "tenant_risk_rows": command_center.get("tenant_churn_risk_rows", [])[:12],
            "stale_support_rows": command_center.get("support_stale_rows", [])[:10],
            "provisioning_breach_rows": command_center.get(
                "provisioning_breach_rows", []
            )[:10],
            "super_dashboard_section_order": get_super_dashboard_section_order(
                request.user
            ),
            "super_dashboard_layout_url": reverse("super:api_super_dashboard_layout"),
            "decision_architecture": get_decision_architecture_for_page(
                "super_dashboard"
            ),
        },
    )
