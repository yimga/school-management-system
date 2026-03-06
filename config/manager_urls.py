"""
Manager host URL configuration (manager.runmycampus.com).
Dedicated for super-admin and operations access.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path

from apps.observability import views as obs_views
from config.admin import admin_site

# Reuse main urlconf error handlers so 500/404/403 pages get user in context (avoids VariableDoesNotExist on manager host).
from config.urls import (
    permission_denied as handler403_view,
    page_not_found as handler404_view,
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


urlpatterns = [
    path("", manager_home, name="home"),
    path("", manager_home, name="manager_home"),
    path("offline/", offline_page, name="offline"),
    path("admin/", admin_site.urls),
    path("authentication/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    path("siteconfig/", include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig")),
    # Namespace registrations so shared backend templates can reverse links on manager host.
    path("evals/", include(("apps.evals.urls", "evals"), namespace="evals")),
    path("academics/", include(("apps.academics.urls", "academics"), namespace="academics")),
    path("portal/", include(("apps.portal.urls", "portal"), namespace="portal")),
    path("reports/", include(("apps.reports.urls", "reports"), namespace="reports")),
    path("finance/", include(("apps.finance.urls", "finance"), namespace="finance")),
    path("communication/", include(("apps.communication.urls", "communication"), namespace="communication")),
    path("api-center/", include(("apps.apicenter.urls", "apicenter"), namespace="apicenter")),
    path("kb/", include(("apps.portal.urls_kb", "kb"), namespace="kb")),
    path("ops/incidents/", obs_views.platform_incidents_console, name="platform_incidents_console"),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("api/health/", obs_views.api_health, name="api_health"),
    path("api/observability/incidents/", obs_views.api_platform_incidents, name="api_platform_incidents"),
    path(
        "api/observability/incidents/<uuid:incident_id>/status/",
        obs_views.api_platform_incident_status,
        name="api_platform_incident_status",
    ),
    path("api/observability/slo-dashboard/", obs_views.api_operational_slo_dashboard, name="api_operational_slo_dashboard"),
    path("api/weather/context/", obs_views.api_weather_context, name="api_weather_context"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
