"""
Manager host URL configuration (manager.runmycampus.com).
Dedicated for super-admin and operations access.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import include, path, reverse

from apps.api.user_preferences_api import ControlPlanePreferencesAPI
from apps.billing import api_views as billing_api_views
from apps.billing.models import TenantSubscription
from apps.observability import views as obs_views
from apps.observability.models import PlatformIncident
from apps.schools.models import School
from apps.schools.marketing_views import marketing_page
from apps.schools.control_plane import (
    require_control_plane_access,
    user_has_control_plane_access,
)
from apps.schools.tenant_url import build_public_absolute_url
from config.admin import platform_admin_site

# Reuse main urlconf error handlers and Phase B legacy redirects.
from config.urls import (
    admin_siteconfig_customizer_redirect,
    page_not_found as handler404_view,
    permission_denied as handler403_view,
    server_error as handler500_view,
    legacy_siteconfig_customizer_redirect,
    legacy_workflow_hub_redirect,
    legacy_report_library_redirect,
)

handler403 = handler403_view
handler404 = handler404_view
handler500 = handler500_view


def manager_home(request):
    if request.user.is_authenticated:
        if user_has_control_plane_access(request.user):
            return redirect("super:dashboard")
        return redirect("accounts:redirect")
    return redirect("accounts:login")


def offline_page(request):
    return render(request, "offline.html", status=200)


def manager_help(request):
    return redirect(build_public_absolute_url(request, "/support/"))


def manager_support_request(request):
    return redirect("super:command_center")


def manager_feedback(request):
    return redirect("super:command_center")


def manager_notifications(request):
    return redirect("super:command_center")


def manager_legacy_surface_redirect(request, surface: str, remaining: str = ""):
    del remaining
    destination = (
        "super:billing_dashboard" if surface == "finance" else "super:dashboard"
    )
    return redirect(destination)


def _subscription_plan_label(subscription: TenantSubscription) -> str:
    plan = getattr(subscription, "plan", None)
    if plan and getattr(plan, "name", None):
        return plan.name
    return "plan"


@require_control_plane_access
def manager_search_api(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        query_lower = query.lower()
        results = []
        static_catalog = _manager_search_static_catalog()
        if not query_lower:
            # Empty query: show a broader intent strip (BR-02 / §8.0.4); catalog includes
            # geography, trust, policy, backlog, fleet, operator hub — not only the first legacy ten.
            results = static_catalog[:22]
        else:
            for item in static_catalog:
                haystack = f"{item['title']} {item['description']} {' '.join(item['meta'])}".lower()
                if query_lower in haystack:
                    results.append(item)
        return JsonResponse({"results": results})

    query_lower = query.lower()
    results: list[dict[str, object]] = []

    static_catalog = _manager_search_static_catalog()
    for item in static_catalog:
        haystack = (
            f"{item['title']} {item['description']} {' '.join(item['meta'])}".lower()
        )
        if query_lower in haystack:
            results.append(item)

    school_matches = School.objects.filter(
        Q(name__icontains=query) | Q(slug__icontains=query)
    ).order_by("name")[:6]
    for school in school_matches:
        results.append(
            {
                "title": school.name,
                "description": f"Tenant {school.slug}",
                "url": f"{reverse('super:dashboard')}?tenant={school.slug}",
                "type": "class",
                "meta": [school.country_code or "Tenant"],
            }
        )

    incident_matches = PlatformIncident.objects.filter(
        Q(title__icontains=query)
        | Q(summary__icontains=query)
        | Q(source_system__icontains=query)
        | Q(incident_type__icontains=query)
    ).order_by("-created_at")[:5]
    for incident in incident_matches:
        results.append(
            {
                "title": incident.title,
                "description": incident.summary
                or incident.source_system
                or "Platform incident",
                "url": reverse("platform_incidents_console"),
                "type": "alert",
                "meta": [incident.status, incident.severity],
            }
        )

    subscription_matches = (
        TenantSubscription.objects.select_related("billing_account__school", "plan")
        .filter(
            Q(status__icontains=query)
            | Q(plan__name__icontains=query)
            | Q(billing_account__school__name__icontains=query)
        )
        .order_by("-updated_at")[:5]
    )
    for subscription in subscription_matches:
        school = getattr(subscription.billing_account, "school", None)
        tenant_slug = getattr(school, "slug", "")
        label = school.name if school else str(subscription.billing_account)
        results.append(
            {
                "title": f"{label} subscription",
                "description": f"{_subscription_plan_label(subscription)} - {subscription.status}",
                "url": f"{reverse('super:billing_dashboard')}?tenant={tenant_slug}",
                "type": "invoice",
                "meta": [subscription.status],
            }
        )

    return JsonResponse({"results": results[:12]})


def _manager_search_static_catalog():
    # §8 Click compression: intents per CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL (≤3 clicks)
    return [
        {
            "title": "Open report library",
            "description": "Report packs, letters, and report card builder hub.",
            "url": f"{reverse('studio_os:output')}?pane=reports",
            "type": "report",
            "meta": ["Studio Output", "Report library"],
        },
        {
            "title": "Feature control",
            "description": "Feature flags and capabilities.",
            "url": reverse("studio_os:control"),
            "type": "class",
            "meta": ["Studio Control", "Feature flags"],
        },
        {
            "title": "Launch checklist",
            "description": "Launch readiness and setup studio.",
            "url": reverse("studio_os:launch"),
            "type": "student",
            "meta": ["Studio Launch", "Setup"],
        },
        {
            "title": "Studio Output",
            "description": "Report library hub, document library, IDs, branding, policy.",
            "url": f"{reverse('studio_os:output')}?pane=reports",
            "type": "report",
            "meta": ["Studio", "Reports"],
        },
        {
            "title": "Tenant Mission Control",
            "description": "Global tenant registry, readiness, and platform posture.",
            "url": reverse("super:dashboard"),
            "type": "report",
            "meta": ["Control plane"],
        },
        {
            "title": "Mission Queues",
            "description": "Approvals, incidents, provisioning breaches, and operator backlog.",
            "url": reverse("super:command_center"),
            "type": "class",
            "meta": ["Queues"],
        },
        {
            "title": "Platform Billing",
            "description": "Subscriptions, trials, and revenue exceptions.",
            "url": reverse("super:billing_dashboard"),
            "type": "invoice",
            "meta": ["Billing"],
        },
        {
            "title": "Marketplace Governance",
            "description": "Publishers, app review queue, kill switches, and revenue-share posture.",
            "url": reverse("super:marketplace_governance"),
            "type": "app",
            "meta": ["Marketplace"],
        },
        {
            "title": "Blueprint Marketplace",
            "description": "Apply policy packs (e.g. Cameroon Francophone, UAE MoE+IB) to a school.",
            "url": reverse("super:blueprint_marketplace"),
            "type": "app",
            "meta": ["Marketplace", "Phase 6"],
        },
        {
            "title": "App Catalog",
            "description": "Install approved marketplace apps for a school.",
            "url": reverse("super:app_catalog"),
            "type": "app",
            "meta": ["Marketplace", "Phase 6"],
        },
        {
            "title": "Platform Incidents",
            "description": "Operator incident console and escalation status.",
            "url": reverse("platform_incidents_console"),
            "type": "alert",
            "meta": ["Observability"],
        },
        {
            "title": "Provision Tenant",
            "description": "Launch the tenant onboarding wizard.",
            "url": reverse("super:create_school_wizard"),
            "type": "student",
            "meta": ["Provisioning"],
        },
        {
            "title": "Geography (region packs)",
            "description": "Wedges 7–13 continent packs, compare US/CAN/GBR, Create school with pack.",
            "url": reverse("super:geography"),
            "type": "class",
            "meta": ["Geography", "Region packs", "Wedges", "GTM"],
        },
        {
            "title": "Trust center",
            "description": "Security & trust hub; residency, compliance, audit export, platform events.",
            "url": reverse("super:trust_center"),
            "type": "class",
            "meta": ["Trust", "Security", "Compliance"],
        },
        {
            "title": "Operator policy",
            "description": "Governance, break-glass, change classes, metrics and automation API pointers.",
            "url": reverse("super:operator_policy"),
            "type": "class",
            "meta": ["Policy", "Governance", "Control plane"],
        },
        {
            "title": "Backlog unlock center",
            "description": "Machine-evaluated gates and program tracks; refresh after merges or CI.",
            "url": reverse("super:backlog_unlock_center"),
            "type": "class",
            "meta": ["Backlog", "Gates", "CI"],
        },
        {
            "title": "Fleet governed changes",
            "description": "Cross-tenant change records and legal status transitions.",
            "url": reverse("super:fleet_governed_changes"),
            "type": "class",
            "meta": ["Fleet", "Governance", "Change"],
        },
        {
            "title": "Platform operator hub",
            "description": "Curated super URLs plus platform-admin changelists in one screen (single-pane entry).",
            "url": reverse("super:platform_operator_hub"),
            "type": "class",
            "meta": ["Operator hub", "Super", "Platform admin"],
        },
    ]


urlpatterns = [
    path("", manager_home, name="home"),
    path("", manager_home, name="manager_home"),
    path("offline/", offline_page, name="offline"),
    path("help/", manager_help, name="manager_help"),
    path("support/", manager_support_request, name="manager_support_request"),
    path("feedback/", manager_feedback, name="manager_feedback"),
    path("notifications/", manager_notifications, name="manager_notifications"),
    path("admin/siteconfig/customizer/", admin_siteconfig_customizer_redirect),
    path("admin/", platform_admin_site.urls),
    path(
        "authentication/",
        include(("apps.accounts.urls", "accounts"), namespace="accounts"),
    ),
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    path("siteconfig/customizer/", legacy_siteconfig_customizer_redirect),
    path("siteconfig/workflow-hub/", legacy_workflow_hub_redirect),
    path("siteconfig/report-library/", legacy_report_library_redirect),
    path("siteconfig/reports/", legacy_report_library_redirect),
    path(
        "siteconfig/",
        include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig"),
    ),
    path(
        "studio/", include(("apps.studio_os.urls", "studio_os"), namespace="studio_os")
    ),
    path(
        "api-center/",
        include(("apps.apicenter.urls", "apicenter"), namespace="apicenter"),
    ),
    path(
        "ops/incidents/",
        obs_views.platform_incidents_console,
        name="platform_incidents_console",
    ),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("api/health/", obs_views.api_health, name="api_health"),
    path(
        "api/control-plane-preferences/",
        ControlPlanePreferencesAPI.as_view(),
        name="api_control_plane_preferences",
    ),
    path("api/search/", manager_search_api, name="manager_search_api"),
    path(
        "api/billing/processors/<str:processor_code>/webhook/",
        billing_api_views.platform_billing_processor_webhook,
        name="platform_billing_processor_webhook",
    ),
    path(
        "api/observability/incidents/",
        obs_views.api_platform_incidents,
        name="api_platform_incidents",
    ),
    path(
        "api/observability/incidents/<uuid:incident_id>/status/",
        obs_views.api_platform_incident_status,
        name="api_platform_incident_status",
    ),
    path(
        "api/observability/slo-dashboard/",
        obs_views.api_operational_slo_dashboard,
        name="api_operational_slo_dashboard",
    ),
    path(
        "api/weather/context/",
        obs_views.api_weather_context,
        name="api_weather_context",
    ),
    path(
        "portal/",
        manager_legacy_surface_redirect,
        {"surface": "portal"},
        name="manager_legacy_portal",
    ),
    path(
        "portal/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "portal"},
    ),
    path(
        "academics/",
        manager_legacy_surface_redirect,
        {"surface": "academics"},
        name="manager_legacy_academics",
    ),
    path(
        "academics/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "academics"},
    ),
    path(
        "evals/",
        manager_legacy_surface_redirect,
        {"surface": "evals"},
        name="manager_legacy_evals",
    ),
    path(
        "evals/<path:remaining>", manager_legacy_surface_redirect, {"surface": "evals"}
    ),
    path(
        "reports/",
        manager_legacy_surface_redirect,
        {"surface": "reports"},
        name="manager_legacy_reports",
    ),
    path(
        "reports/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "reports"},
    ),
    path(
        "finance/",
        manager_legacy_surface_redirect,
        {"surface": "finance"},
        name="manager_legacy_finance",
    ),
    path(
        "finance/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "finance"},
    ),
    path(
        "communication/",
        manager_legacy_surface_redirect,
        {"surface": "communication"},
        name="manager_legacy_communication",
    ),
    path(
        "communication/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "communication"},
    ),
    path("kb/", include(("apps.portal.urls_kb", "kb"), namespace="kb")),
    path(
        "legacy-kb/",
        manager_legacy_surface_redirect,
        {"surface": "kb"},
        name="manager_legacy_kb",
    ),
    path("legacy-kb/<path:remaining>", manager_legacy_surface_redirect, {"surface": "kb"}),
    path(
        "analytics/",
        manager_legacy_surface_redirect,
        {"surface": "analytics"},
        name="manager_legacy_analytics",
    ),
    path(
        "analytics/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "analytics"},
    ),
    path(
        "compliance/",
        manager_legacy_surface_redirect,
        {"surface": "compliance"},
        name="manager_legacy_compliance",
    ),
    path(
        "compliance/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "compliance"},
    ),
    path(
        "payroll/",
        manager_legacy_surface_redirect,
        {"surface": "payroll"},
        name="manager_legacy_payroll",
    ),
    path(
        "payroll/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "payroll"},
    ),
    path(
        "privacy/", marketing_page, {"page_slug": "privacy"}, name="marketing_privacy"
    ),
    path("terms/", marketing_page, {"page_slug": "terms"}, name="marketing_terms"),
    path(
        "cookie-policy/",
        marketing_page,
        {"page_slug": "cookie-policy"},
        name="marketing_cookie_policy",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
