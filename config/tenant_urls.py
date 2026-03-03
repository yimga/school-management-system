"""
Tenant (school app) URL configuration for subdomain or /t/<slug>/.
Used when request.urlconf is set to this module by UrlConfSwitcherMiddleware.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.urls import include, path
from django.views.decorators.cache import cache_page
from rest_framework.schemas import get_schema_view
from django.contrib.auth.decorators import login_required, user_passes_test
from django.template.response import TemplateResponse
from django.http import HttpResponseForbidden
from django.shortcuts import render

from apps.siteconfig.models import SiteSettings
from apps.observability import views as obs_views
from apps.portal.views_ai_copilot import (
    ai_copilot_query,
    ai_permissions,
    ai_copilot_limits,
    ai_copilot_config,
    ai_copilot_audit_feed,
)
from config.admin import admin_site
from apps.schools.section8_views import frozen_account
from apps.schools.views_domains import api_domains_list_or_create, api_domains_verify


def home(request):
    if request.user.is_authenticated:
        return redirect("accounts:redirect")
    return redirect("accounts:login")


def _is_schema_allowed(user):
    role = (getattr(user, "role", "") or "").upper()
    return user.is_authenticated and (user.is_staff or user.is_superuser or role in {"ADMIN", "IT_ADMIN", "LEADERSHIP"})


@login_required
@user_passes_test(_is_schema_allowed)
def api_schema_ui(request):
    flags = getattr(SiteSettings.get_solo(), "backend_feature_flags", {}) or {}
    allowed_roles = [str(r).upper() for r in flags.get("allowed_roles_api_schema", [])]
    if not flags.get("enable_api_schema_ui", True):
        return HttpResponseForbidden("API schema UI disabled by admin.")
    if allowed_roles:
        role = (getattr(request.user, "role", "") or "").upper()
        if role not in allowed_roles and not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("You are not allowed to access API schema UI.")
    from django.urls import reverse
    return TemplateResponse(request, "api_schema_ui.html", {"schema_url": reverse("api-schema")})


_schema_view_raw = cache_page(60)(get_schema_view(
    title="RunMyCampus API",
    description="Entity/analytics/session claims schema for frontend orchestration",
    version="1.0.0",
))


@login_required
@user_passes_test(_is_schema_allowed)
def schema_view(request):
    return _schema_view_raw(request)


def admin_siteconfig_customizer_redirect(request):
    return redirect("/siteconfig/customizer/")


def permission_denied(request, exception):
    is_admin_forbidden = (
        request.path.startswith("/admin")
        and request.user.is_authenticated
        and request.user.is_staff
        and not request.user.is_superuser
    )
    return render(request, "errors/403.html", {"is_admin_forbidden": is_admin_forbidden}, status=403)


def page_not_found(request, exception):
    from apps.schools.error_views import school_not_found
    return school_not_found(request)


def server_error(request):
    return render(request, "errors/500.html", status=500)


handler403 = permission_denied
handler404 = page_not_found
handler500 = server_error

urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin_site.urls),
    path("api/schema/", schema_view, name="api-schema"),
    path("api/schema/ui/", api_schema_ui, name="api-schema-ui"),
    path("backend/", lambda request: redirect("accounts:backend_dashboard", permanent=False)),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("metrics/", obs_views.metrics, name="metrics"),
    path("api/observability/copilot-metrics/", obs_views.copilot_metrics_json, name="copilot_metrics_json"),
    path("api/observability/slo-dashboard/", obs_views.api_operational_slo_dashboard, name="api_operational_slo_dashboard"),
    path("admin/dashboard/", obs_views.admin_dashboard, name="admin_dashboard"),
    path("api/health/", obs_views.api_health, name="api_health"),
    path("api/admin/weather/", obs_views.api_admin_weather, name="api_admin_weather"),
    path("api/weather/context/", obs_views.api_weather_context, name="api_weather_context"),
    path("api/notifications/", obs_views.api_notifications, name="api_notifications"),
    path("api/notifications/mark-all-read/", obs_views.api_notifications_mark_all_read, name="api_notifications_mark_all_read"),
    path("api/activities/", obs_views.api_activities, name="api_activities"),
    path("api/dashboard/charts/", obs_views.api_dashboard_charts, name="api_dashboard_charts"),
    path("api/ai-copilot/validate/", ai_copilot_query, name="ai_copilot_query"),
    path("api/ai-copilot/permissions/", ai_permissions, name="ai_permissions"),
    path("api/ai-copilot/limits/", ai_copilot_limits, name="ai_copilot_limits"),
    path("api/ai-copilot/config/", ai_copilot_config, name="ai_copilot_config"),
    path("api/ai-copilot/audit/", ai_copilot_audit_feed, name="ai_copilot_audit"),
    path("admin/siteconfig/customizer/", admin_siteconfig_customizer_redirect),
    path("verify/<str:token>/", __import__("apps.siteconfig.views_verify", fromlist=["verify_student_id"]).verify_student_id, name="verify_student_id"),
    path("api/", include(("apps.api.urls", "api"), namespace="api")),
    path("api/v1/", include(("apps.api.urls_v1", "api_v1"), namespace="api_v1")),
    path("siteconfig/", include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig")),
    path("api-center/", include(("apps.apicenter.urls", "apicenter"), namespace="apicenter")),
    path("authentication/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("evals/", include(("apps.evals.urls", "evals"), namespace="evals")),
    path("academics/", include(("apps.academics.urls", "academics"), namespace="academics")),
    path("portal/", include(("apps.portal.urls", "portal"), namespace="portal")),
    path("portal", lambda request: redirect("portal:parent_dashboard")),
    path("kb/", include(("apps.portal.urls_kb", "kb"), namespace="kb")),
    path("reports/", include(("apps.reports.urls", "reports"), namespace="reports")),
    path("analytics/", include(("apps.analytics.urls", "analytics"), namespace="analytics")),
    path("finance/", include(("apps.finance.urls", "finance"), namespace="finance")),
    path("payroll/", include(("apps.payroll.urls", "payroll"), namespace="payroll")),
    path("compliance/", include(("apps.compliance.urls", "compliance"), namespace="compliance")),
    path("communication/", include(("apps.communication.urls", "communication"), namespace="communication")),
    path("emis/", include(("emis.urls", "emis"), namespace="emis")),
    path("requests/", include(("apps.requests.urls", "requests"), namespace="requests")),
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    path("api/tenant/domains/", api_domains_list_or_create, name="api_domains_list_or_create"),
    path("api/tenant/domains/<uuid:school_domain_id>/verify/", api_domains_verify, name="api_domains_verify"),
    path("account-frozen/", frozen_account, name="account_frozen"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
