"""
Super dashboard v1/v2 and layout API (BR-12 split from super_views).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.db.models import Count, Sum
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.platform_runtime.models import PlatformOperatorSuperDashboardLink
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)
from .decision_architecture import get_decision_architecture_for_page
from .models import School
from .super_dashboard_cache import (
    get_cached_command_center_data,
    get_cached_fleet_registry_metrics,
    get_cached_health_table_metadata,
    get_cached_platform_health,
    get_cached_registry_counts,
)
from .super_views_constants import CONTROL_PLANE_METRIC_FAILURES
from .super_views_dashboard_helpers import (
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
from .super_dashboard_registry import (
    REGISTRY_PAGE_SIZE_OPTIONS,
    build_registry_queryset,
    enrich_school_for_registry,
    load_brand_profile_ids,
    load_country_names,
    paginate_registry,
)

_DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "debug-0f968b.log"


def _agent_debug_log(
    hypothesis_id: str, location: str, message: str, data: dict | None = None
) -> None:
    import os

    if os.environ.get("RMC_AGENT_DEBUG", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    # region agent log
    try:
        import json as _json

        payload = {
            "sessionId": "0f968b",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    # endregion


def _optional_reverse_for_request(request, name: str) -> str:
    try:
        return reverse(name, urlconf=getattr(request, "urlconf", None))
    except NoReverseMatch:
        return ""


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
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

@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_dashboard_v2(request):
    """Mission-control control plane for the manager host."""
    t0 = time.perf_counter()
    if request.method == "POST":
        # Stray POST (browser resubmit) must not rebuild ~600KB HTML on a sync/gthread worker.
        _agent_debug_log(
            "H-POST",
            "super_views_dashboard_surfaces.super_dashboard_v2",
            "post_redirect_prg",
            {"path": request.path, "query": request.META.get("QUERY_STRING", "")},
        )
        target = request.get_full_path() or reverse("super:dashboard")
        return HttpResponseRedirect(target)

    from apps.billing.models import BillingAccount, TenantSubscription
    from apps.events.legacy_bridge import legacy_webhook_sync_snapshot
    from apps.observability.models import PlatformIncident
    from apps.siteconfig.models import RevenueSnapshot

    first_of_month = parse_month_param(request)
    month_options = build_month_options_list(12)
    current_request_month = first_of_month.strftime("%Y-%m")

    country_names = load_country_names()
    brand_profile_ids = load_brand_profile_ids()

    total_mrr = total_waived = waiver_percentage = 0
    revenue_by_country = []
    billing_model_breakdown = []
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
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
        .annotate(student_count=Count("student_profiles", distinct=True))[:50]
    )
    for school in pending_schools:
        school.timeline_url = safe_school_timeline_url(school.pk)
        school.selected_systems = selected_system_names(school)
        school.country_display = country_names.get(
            school.canonical_country_code, school.canonical_country_code or "Unassigned"
        )
    pending_approval_count = School.objects.filter(is_approved=False).count()

    health_top_tables, health_schema_stats = get_cached_health_table_metadata()

    command_center = get_cached_command_center_data()
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
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        .order_by("-updated_at", "school__name")[:12]
    )
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    active_subscription_count = TenantSubscription.objects.filter(
        status__in=[
            TenantSubscription.Status.ACTIVE,
            TenantSubscription.Status.TRIALING,
        ]
    ).count()
    billing_account_count = BillingAccount.objects.count()
    webhook_stack = legacy_webhook_sync_snapshot()
    platform_health = get_cached_platform_health()

    registry_counts = get_cached_registry_counts()
    churn_risk_lookup = {
        str(row["school"].id): row
        for row in command_center.get("tenant_churn_risk_rows", [])
        if row.get("school") is not None
    }
    churn_risk_school_ids = {
        row["school"].pk
        for row in command_center.get("tenant_churn_risk_rows", [])
        if row.get("school") is not None
    }
    incident_school_ids = {
        incident.affected_school_id
        for incident in platform_incidents
        if getattr(incident, "affected_school_id", None)
    }
    fleet_metrics = get_cached_fleet_registry_metrics(
        incident_school_ids=incident_school_ids,
        churn_risk_school_ids=churn_risk_school_ids,
    )
    school_count = fleet_metrics.school_count
    identity_complete_count = fleet_metrics.identity_complete_count
    brand_profile_count = fleet_metrics.brand_profile_count
    verified_domain_count = fleet_metrics.verified_domain_count
    custom_domain_count = fleet_metrics.custom_domain_count
    impersonation_ready_count = fleet_metrics.impersonation_ready_count
    attention_school_count = fleet_metrics.attention_school_count
    countries_live_count = fleet_metrics.countries_live_count

    (
        registry_page,
        registry_search,
        registry_state,
        registry_page_size,
        registry_pagination_extra_query,
    ) = paginate_registry(
        request,
        incident_school_ids=incident_school_ids,
        churn_risk_school_ids=churn_risk_school_ids,
        churn_risk_lookup=churn_risk_lookup,
        country_names=country_names,
        brand_profile_ids=brand_profile_ids,
    )
    schools = list(registry_page.object_list)

    recent_schools = list(
        build_registry_queryset().order_by("-created_at", "name")[:8]
    )
    for school in recent_schools:
        enrich_school_for_registry(
            school,
            country_names=country_names,
            brand_profile_ids=brand_profile_ids,
            incident_school_ids=incident_school_ids,
            churn_risk_lookup=churn_risk_lookup,
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
            "meta": f"{fleet_metrics.active_school_count} active / {pending_approval_count} pending approval",
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
    migration_start_url = _optional_reverse_for_request(
        request, "migration_cloud_super:bundle_new"
    )
    migration_health_url = _optional_reverse_for_request(
        request, "migration_cloud_super:migration_cloud_health"
    )
    proof_surface_cards = []
    for card in (
        {
            "title": "Public-to-Product matrix",
            "metric": "Proof",
            "meta": "Public claims mapped to product routes and delivery proof",
            "url": _optional_reverse_for_request(
                request, "manager_public_to_product_matrix"
            ),
            "cta": "Open matrix",
        },
        {
            "title": "Feature gap register",
            "metric": "Gaps",
            "meta": "Feature status, proof route, model, command, and CI coverage",
            "url": _optional_reverse_for_request(
                request, "manager_feature_gap_register"
            ),
            "cta": "Review gaps",
        },
        {
            "title": "Feedback loop",
            "metric": "Live",
            "meta": "Friction, feedback, and AI-assistant adoption signals",
            "url": _optional_reverse_for_request(request, "manager_feedback_loop"),
            "cta": "Inspect signals",
        },
        {
            "title": "Lane-2 readiness",
            "metric": "External",
            "meta": "PSP, SOC2 evidence, and pilot readiness in one scoreboard",
            "url": _optional_reverse_for_request(request, "manager_lane2_readiness"),
            "cta": "Check readiness",
        },
    ):
        if card["url"]:
            proof_surface_cards.append(card)

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
            "title": "Migration Cloud",
            "metric": "Ready" if migration_start_url else "Summary",
            "meta": "Intake, profile registry, health, audit, tokens, and webhook operations",
            "url": migration_start_url or reverse("super:migration_cloud"),
            "cta": "Open migration",
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
    ] + proof_surface_cards
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
        {
            "label": "Migration Cloud ops",
            "value": "Health" if migration_health_url else "Summary",
            "meta": "Wizard intake, health, audit, tokens, and webhooks are linked from the dashboard",
            "tone": "success" if migration_health_url else "neutral",
        },
        {
            "label": "Operator proof surfaces",
            "value": f"{len(proof_surface_cards)}/4",
            "meta": "Public promises, feature gaps, feedback, and Lane-2 readiness exposed",
            "tone": "success" if len(proof_surface_cards) == 4 else "warning",
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

    from apps.schools.dashboard_topology_registry import filter_operational_dashboard_links

    operator_super_dashboard_links = filter_operational_dashboard_links(
        PlatformOperatorSuperDashboardLink.objects.order_by("sort_order", "slug")
    )
    from apps.schools.super_views_operator_team import operator_peer_picker_context

    peer_operators = operator_peer_picker_context(
        exclude_user_id=request.user.pk if request.user.is_authenticated else None
    )
    from apps.schools.residency_readiness import assess_readiness

    data_residency_readiness = assess_readiness()
    response = render(
        request,
        "schools/super_dashboard.html",
        {
            "schools": schools,
            "registry_page": registry_page,
            "registry_search": registry_search,
            "registry_state": registry_state,
            "registry_page_size": registry_page_size,
            "registry_page_size_options": REGISTRY_PAGE_SIZE_OPTIONS,
            "registry_pagination_extra_query": registry_pagination_extra_query,
            "registry_total_count": registry_page.paginator.count,
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
            "operator_super_dashboard_links": operator_super_dashboard_links,
            "peer_operators": peer_operators,
            "data_residency_readiness": data_residency_readiness,
        },
    )
    _agent_debug_log(
        "H-LOAD",
        "super_views_dashboard_surfaces.super_dashboard_v2",
        "dashboard_render_complete",
        {
            "method": request.method,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "registry_total_count": registry_page.paginator.count,
        },
    )
    return response
