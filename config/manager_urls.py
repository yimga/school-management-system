"""
Manager host URL configuration (manager.runmycampus.com).
Dedicated for super-admin and operations access.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import include, path, reverse

from apps.billing import api_views as billing_api_views
from apps.billing.models import TenantSubscription
from apps.observability import views as obs_views
from apps.observability.models import PlatformIncident
from apps.schools.models import School
from apps.schools.tenant_url import build_public_absolute_url
from config.admin import admin_site

# Reuse main urlconf error handlers so 500/404/403 pages get user in context.
from config.urls import (
    page_not_found as handler404_view,
    permission_denied as handler403_view,
    server_error as handler500_view,
)

handler403 = handler403_view
handler404 = handler404_view
handler500 = handler500_view


def manager_home(request):
    if request.user.is_authenticated:
        return redirect("super:dashboard")
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
    destination = "super:billing_dashboard" if surface == "finance" else "super:dashboard"
    return redirect(destination)


def _portal_link_child_redirect(request):
    """Manager has no portal link-child flow; send to claim-invite so login page URL resolves."""
    return redirect("accounts:claim_invite")


portal_compat_patterns = [
    path("", manager_legacy_surface_redirect, {"surface": "portal"}, name="home"),
    path("parent/", manager_legacy_surface_redirect, {"surface": "portal"}, name="parent_dashboard"),
    path("parent/link-child/", _portal_link_child_redirect, name="link_child"),
    path("teacher/", manager_legacy_surface_redirect, {"surface": "portal"}, name="teacher_dashboard_alias"),
    path("support/request/", manager_legacy_surface_redirect, {"surface": "portal"}, name="support_request"),
]

kb_compat_patterns = [
    path("", manager_legacy_surface_redirect, {"surface": "kb"}, name="kb_home"),
    path("faq/", manager_legacy_surface_redirect, {"surface": "kb"}, name="faq_list"),
]

finance_compat_patterns = [
    path("", manager_legacy_surface_redirect, {"surface": "finance"}, name="dashboard"),
    path("invoices/", manager_legacy_surface_redirect, {"surface": "finance"}, name="invoices"),
]

evals_compat_patterns = [
    path("", manager_legacy_surface_redirect, {"surface": "evals"}, name="home"),
    path("teacher/", manager_legacy_surface_redirect, {"surface": "evals"}, name="teacher_dashboard"),
    path("marks-entry/", manager_legacy_surface_redirect, {"surface": "evals"}, name="teacher_marks_entry"),
    path("admin/", manager_legacy_surface_redirect, {"surface": "evals"}, name="evaluation_admin"),
]

analytics_compat_patterns = [
    path("", manager_legacy_surface_redirect, {"surface": "reports"}, name="dashboard"),
]

compliance_compat_patterns = [
    path("", manager_legacy_surface_redirect, {"surface": "reports"}, name="dashboard"),
]

payroll_compat_patterns = [
    path("", manager_legacy_surface_redirect, {"surface": "reports"}, name="dashboard"),
]


def _subscription_plan_label(subscription: TenantSubscription) -> str:
    plan = getattr(subscription, "plan", None)
    if plan and getattr(plan, "name", None):
        return plan.name
    return "plan"


@login_required
def manager_search_api(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    query_lower = query.lower()
    results: list[dict[str, object]] = []

    static_catalog = [
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
    ]

    for item in static_catalog:
        haystack = f"{item['title']} {item['description']} {' '.join(item['meta'])}".lower()
        if query_lower in haystack:
            results.append(item)

    school_matches = School.objects.filter(Q(name__icontains=query) | Q(slug__icontains=query)).order_by("name")[:6]
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

    incident_matches = (
        PlatformIncident.objects.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(source_system__icontains=query)
            | Q(incident_type__icontains=query)
        )
        .order_by("-created_at")[:5]
    )
    for incident in incident_matches:
        results.append(
            {
                "title": incident.title,
                "description": incident.summary or incident.source_system or "Platform incident",
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


urlpatterns = [
    path("", manager_home, name="home"),
    path("", manager_home, name="manager_home"),
    path("offline/", offline_page, name="offline"),
    path("help/", manager_help, name="manager_help"),
    path("support/", manager_support_request, name="manager_support_request"),
    path("feedback/", manager_feedback, name="manager_feedback"),
    path("notifications/", manager_notifications, name="manager_notifications"),
    path("admin/", admin_site.urls),
    path("authentication/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    path("siteconfig/", include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig")),
    path("api-center/", include(("apps.apicenter.urls", "apicenter"), namespace="apicenter")),
    path("ops/incidents/", obs_views.platform_incidents_console, name="platform_incidents_console"),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("api/health/", obs_views.api_health, name="api_health"),
    path("api/search/", manager_search_api, name="manager_search_api"),
    path(
        "api/billing/processors/<str:processor_code>/webhook/",
        billing_api_views.platform_billing_processor_webhook,
        name="platform_billing_processor_webhook",
    ),
    path("api/observability/incidents/", obs_views.api_platform_incidents, name="api_platform_incidents"),
    path(
        "api/observability/incidents/<uuid:incident_id>/status/",
        obs_views.api_platform_incident_status,
        name="api_platform_incident_status",
    ),
    path("api/observability/slo-dashboard/", obs_views.api_operational_slo_dashboard, name="api_operational_slo_dashboard"),
    path("api/weather/context/", obs_views.api_weather_context, name="api_weather_context"),
    path("portal/", manager_legacy_surface_redirect, {"surface": "portal"}, name="manager_legacy_portal"),
    path("portal/<path:remaining>", manager_legacy_surface_redirect, {"surface": "portal"}),
    path("portal/", include((portal_compat_patterns, "portal"), namespace="portal")),
    path("academics/", manager_legacy_surface_redirect, {"surface": "academics"}, name="manager_legacy_academics"),
    path("academics/<path:remaining>", manager_legacy_surface_redirect, {"surface": "academics"}),
    path("evals/", manager_legacy_surface_redirect, {"surface": "evals"}, name="manager_legacy_evals"),
    path("evals/<path:remaining>", manager_legacy_surface_redirect, {"surface": "evals"}),
    path("evals/", include((evals_compat_patterns, "evals"), namespace="evals")),
    path("reports/", manager_legacy_surface_redirect, {"surface": "reports"}, name="manager_legacy_reports"),
    path("reports/<path:remaining>", manager_legacy_surface_redirect, {"surface": "reports"}),
    path("finance/", manager_legacy_surface_redirect, {"surface": "finance"}, name="manager_legacy_finance"),
    path("finance/<path:remaining>", manager_legacy_surface_redirect, {"surface": "finance"}),
    path("finance/", include((finance_compat_patterns, "finance"), namespace="finance")),
    path("communication/", manager_legacy_surface_redirect, {"surface": "communication"}, name="manager_legacy_communication"),
    path("communication/<path:remaining>", manager_legacy_surface_redirect, {"surface": "communication"}),
    path("kb/", manager_legacy_surface_redirect, {"surface": "kb"}, name="manager_legacy_kb"),
    path("kb/<path:remaining>", manager_legacy_surface_redirect, {"surface": "kb"}),
    path("kb/", include((kb_compat_patterns, "kb"), namespace="kb")),
    path("analytics/", include((analytics_compat_patterns, "analytics"), namespace="analytics")),
    path("compliance/", include((compliance_compat_patterns, "compliance"), namespace="compliance")),
    path("payroll/", include((payroll_compat_patterns, "payroll"), namespace="payroll")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
