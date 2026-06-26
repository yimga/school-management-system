"""
Super dashboard v1/v2 and layout API (BR-12 split from super_views).
"""

from __future__ import annotations

import json
import time

from django.db.models import Count, Sum
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.formats import number_format
from django.utils.translation import gettext as _, ngettext

from apps.platform_runtime.models import PlatformOperatorSuperDashboardLink
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)
from apps.siteconfig.currency import platform_currency_symbol

from .decision_architecture import get_decision_architecture_for_page
from .models import School
from .super_dashboard_cache import (
    get_cached_country_rollup,
    get_cached_command_center_data,
    get_cached_fleet_registry_metrics,
    get_cached_health_table_metadata,
    get_cached_incident_bundle,
    get_cached_legacy_webhook_stack,
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
    timings: dict[str, int] = {}
    if request.method == "POST":
        # Stray POST (browser resubmit) must not rebuild ~600KB HTML on a sync/gthread worker.
        target = request.get_full_path() or reverse("super:dashboard")
        return HttpResponseRedirect(target)

    from apps.billing.models import BillingAccount, TenantSubscription
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
    timings["revenue_snapshot_ms"] = int((time.perf_counter() - t0) * 1000)

    pending_schools = list(
        School.objects.filter(is_approved=False)
        .prefetch_related("tenant_systems__system")
        .order_by("-created_at")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))[:20]
    )
    for school in pending_schools:
        school.timeline_url = safe_school_timeline_url(school.pk)
        school.selected_systems = selected_system_names(school)
        school.country_display = country_names.get(
            school.canonical_country_code, school.canonical_country_code or "Unassigned"
        )
    pending_approval_count = School.objects.filter(is_approved=False).count()
    timings["pending_queue_ms"] = int((time.perf_counter() - t0) * 1000)

    health_top_tables, health_schema_stats = get_cached_health_table_metadata()

    command_center = get_cached_command_center_data()
    provisioning_breach_rows = list(
        command_center.get("provisioning_breach_rows", [])[:10]
    )
    if provisioning_breach_rows:
        breach_ids = [
            row["school_id"]
            for row in provisioning_breach_rows
            if row.get("school_id")
        ]
        breach_school_map = {
            s.id: s
            for s in School.objects.filter(id__in=breach_ids).only("id", "name", "slug")
        }
        for row in provisioning_breach_rows:
            row["school"] = breach_school_map.get(row.get("school_id"))
    incident_bundle = get_cached_incident_bundle()
    platform_incidents = incident_bundle.get("platform_incidents", [])
    incident_counts = incident_bundle.get("incident_counts", {})
    critical_incident_count = int(incident_bundle.get("critical_incident_count", 0) or 0)
    timings["incident_bundle_ms"] = int((time.perf_counter() - t0) * 1000)
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
    webhook_stack = get_cached_legacy_webhook_stack()
    platform_health = get_cached_platform_health()
    timings["billing_health_ms"] = int((time.perf_counter() - t0) * 1000)

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
        incident.get("affected_school_id")
        for incident in platform_incidents
        if incident.get("affected_school_id")
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

    country_rollup = get_cached_country_rollup()
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
    timings["country_rollup_ms"] = int((time.perf_counter() - t0) * 1000)

    cur = platform_currency_symbol()
    if total_mrr is not None and total_mrr > 0:
        north_star_label = _("Total MRR")
        north_star_formatted = f"{cur}{number_format(total_mrr, decimal_pos=2, force_grouping=True)}"
    else:
        north_star_label = _("Schools")
        north_star_formatted = str(school_count)

    next_best_actions = []
    if pending_approval_count:
        next_best_actions.append(
            {
                "label": ngettext(
                    "%(count)s pending approval",
                    "%(count)s pending approvals",
                    pending_approval_count,
                )
                % {"count": pending_approval_count},
                "url": request.path + "#cp-action-queue",
                "count": pending_approval_count,
            }
        )
    if command_center.get("trial_ending_soon_count", 0):
        cc_url = safe_command_center_url()
        trial_count = command_center["trial_ending_soon_count"]
        if cc_url:
            next_best_actions.append(
                {
                    "label": ngettext(
                        "%(count)s trial ending soon",
                        "%(count)s trials ending soon",
                        trial_count,
                    )
                    % {"count": trial_count},
                    "url": cc_url,
                    "count": trial_count,
                }
            )
    if command_center.get("provisioning_sla_breaches", 0):
        cc_url = safe_command_center_url()
        breach_count = command_center["provisioning_sla_breaches"]
        if cc_url:
            next_best_actions.append(
                {
                    "label": ngettext(
                        "%(count)s provisioning breach",
                        "%(count)s provisioning breaches",
                        breach_count,
                    )
                    % {"count": breach_count},
                    "url": cc_url,
                    "count": breach_count,
                }
            )
    if platform_incidents:
        incident_count = len(platform_incidents)
        next_best_actions.append(
            {
                "label": ngettext(
                    "%(count)s live incident",
                    "%(count)s live incidents",
                    incident_count,
                )
                % {"count": incident_count},
                "url": safe_platform_incidents_url() or request.path,
                "count": incident_count,
            }
        )

    migration_start_url = _optional_reverse_for_request(
        request, "migration_cloud_super:bundle_new"
    )
    migration_health_url = _optional_reverse_for_request(
        request, "migration_cloud_super:migration_cloud_health"
    )
    proof_surface_cards = []
    for card in (
        {
            "title": _("Public-to-Product matrix"),
            "metric": _("Proof"),
            "meta": _(
                "Public claims mapped to product routes and delivery proof"
            ),
            "url": _optional_reverse_for_request(
                request, "manager_public_to_product_matrix"
            ),
            "cta": _("Open matrix"),
        },
        {
            "title": _("Feature gap register"),
            "metric": _("Gaps"),
            "meta": _(
                "Feature status, proof route, model, command, and CI coverage"
            ),
            "url": _optional_reverse_for_request(
                request, "manager_feature_gap_register"
            ),
            "cta": _("Review gaps"),
        },
        {
            "title": _("Feedback loop"),
            "metric": _("Live"),
            "meta": _("Friction, feedback, and AI-assistant adoption signals"),
            "url": _optional_reverse_for_request(request, "manager_feedback_loop"),
            "cta": _("Inspect signals"),
        },
        {
            "title": _("Lane-2 readiness"),
            "metric": _("External"),
            "meta": _("PSP, SOC2 evidence, and pilot readiness in one scoreboard"),
            "url": _optional_reverse_for_request(request, "manager_lane2_readiness"),
            "cta": _("Check readiness"),
        },
    ):
        if card["url"]:
            proof_surface_cards.append(card)

    workstream_cards = [
        {
            "title": _("Mission queues"),
            "metric": pending_approval_count
            + command_center.get("support_backlog_48h_count", 0)
            + len(platform_incidents),
            "meta": _(
                "Approvals, stale support, incidents, and provisioning breaches"
            ),
            "url": safe_command_center_url(),
            "cta": _("Open queues"),
        },
        {
            "title": _("Platform billing"),
            "metric": active_subscription_count,
            "meta": ngettext(
                "%(count)s tenant needs billing attention",
                "%(count)s tenants need billing attention",
                len(billing_watchlist),
            )
            % {"count": len(billing_watchlist)},
            "url": reverse("super:billing_dashboard"),
            "cta": _("Inspect billing"),
        },
        {
            "title": _("Incident console"),
            "metric": len(platform_incidents),
            "meta": ngettext(
                "%(count)s critical/high severity incident",
                "%(count)s critical/high severity incidents",
                critical_incident_count,
            )
            % {"count": critical_incident_count},
            "url": safe_platform_incidents_url(),
            "cta": _("Review incidents"),
        },
        {
            "title": _("Usage and quotas"),
            "metric": command_center.get("tenant_churn_risk_count", 0),
            "meta": _("Usage posture, risk watchlist, and adoption signals"),
            "url": reverse("super:usage"),
            "cta": _("View usage"),
        },
        {
            "title": _("Migration Cloud"),
            "metric": _("Ready") if migration_start_url else _("Summary"),
            "meta": _(
                "Intake, profile registry, health, audit, tokens, and webhook operations"
            ),
            "url": migration_start_url or reverse("super:migration_cloud"),
            "cta": _("Open migration"),
        },
        {
            "title": _("Fleet health"),
            "metric": str(platform_health.get("overall_status", "unknown")).upper(),
            "meta": _("Webhook drift groups: %(count)s")
            % {"count": webhook_stack.get("unsynced_legacy_groups", 0)},
            "url": reverse("super:tenant_health"),
            "cta": _("Audit tenants"),
        },
        {
            "title": _("Health hub"),
            "metric": "—",
            "meta": _("Runbooks, SLOs, incidents, tenant health"),
            "url": reverse("super:control_health"),
            "cta": _("Health hub"),
        },
        {
            "title": _("Tenant Studio"),
            "metric": registry_counts["education_system_types"],
            "meta": _(
                "Registry-backed onboarding with branding and control-plane defaults"
            ),
            "url": reverse("super:create_school_wizard"),
            "cta": _("Open tenant studio"),
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
    from apps.schools.fleet_status import format_fleet_summary_label, resolve_fleet_summary

    proof_ledger_url = _optional_reverse_for_request(
        request, "manager_public_to_product_matrix"
    ) or _optional_reverse_for_request(request, "manager_feature_gap_register")
    cockpit_export_pdf_url = reverse("super:export_super_dashboard_pdf")
    if current_request_month:
        cockpit_export_pdf_url = f"{cockpit_export_pdf_url}?month={current_request_month}"

    request.rmc_cp_globe_landing_minimal_chrome = True
    request.rmc_cp_globe_deck_v2 = True
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
            "workstream_cards": workstream_cards,
            "readiness_cards": readiness_cards,
            "attention_school_count": attention_school_count,
            "recent_schools": recent_schools,
            "tenant_risk_rows": command_center.get("tenant_churn_risk_rows", [])[:12],
            "stale_support_rows": command_center.get("support_stale_rows", [])[:10],
            "provisioning_breach_rows": provisioning_breach_rows,
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
            "fleet_summary_label": format_fleet_summary_label(resolve_fleet_summary()),
            "rmc_cp_globe_landing_minimal_chrome": True,
            "rmc_cp_globe_deck_v2": True,
            "proof_ledger_url": proof_ledger_url,
            "cockpit_export_pdf_url": cockpit_export_pdf_url,
        },
    )
    response["X-RMC-SuperDashboard-Elapsed-Ms"] = str(
        int((time.perf_counter() - t0) * 1000)
    )
    return response
