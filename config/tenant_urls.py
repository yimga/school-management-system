"""
Tenant (school app) URL configuration for subdomain or /t/<slug>/.
Used when request.urlconf is set to this module by UrlConfSwitcherMiddleware.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.shortcuts import redirect
from django.urls import include, path
from django.views.decorators.cache import cache_page
from rest_framework.schemas import get_schema_view
from django.contrib.auth.decorators import login_required, user_passes_test
from django.template.response import TemplateResponse
from django.http import HttpResponseForbidden
from django.shortcuts import render

from apps.platform_runtime.helpers import get_effective_flags
from apps.observability import views as obs_views
from apps.portal.views_ai_copilot import (
    ai_copilot_query,
    ai_permissions,
    ai_copilot_limits,
    ai_copilot_config,
    ai_copilot_audit_feed,
)
from config.admin import tenant_admin_site
from apps.schools.activation_views import activation_first_action
from apps.schools.demo_conversion_views import (
    demo_flow_attendance,
    demo_flow_attendance_complete,
    demo_flow_complete,
    demo_flow_index,
    demo_flow_marks,
    demo_flow_marks_complete,
    demo_flow_report,
    demo_flow_report_complete,
)
from apps.schools.section8_views import frozen_account
from apps.schools.parent_tenant_views import parent_tenant_dashboard
from apps.schools.views_domains import api_domains_list_or_create, api_domains_verify
from apps.schools.marketing_views import marketing_page
from apps.marketplace.views import (
    tenant_installed_apps,
    tenant_app_catalog,
    tenant_install_impact_preview,
    tenant_install_app,
    tenant_uninstall_app,
    tenant_scope_consent,
    tenant_approve_scope,
    tenant_save_installation_config,
    tenant_activate_installation,
)
from apps.platform_runtime.views_click_tracking import (
    click_measurement_dashboard,
    record_click_event,
)
from apps.platform_runtime.views_administration import (
    internal_admin_alias_redirect,
    school_configuration_center,
    tenant_blueprint_setup,
    tenant_pack_setup,
    tenant_configuration_forbidden,
)


def home(request):
    if request.user.is_authenticated:
        return redirect("accounts:redirect")
    return redirect("accounts:login")


def favicon_redirect(request):
    """Serve favicon by redirecting to default static icon; avoids 500 when 404 pipeline runs for /favicon.ico."""
    return redirect(static("images/runmycampus-icon.png"), permanent=False)


def _is_schema_allowed(user):
    role = (getattr(user, "role", "") or "").upper()
    return user.is_authenticated and (
        user.is_staff
        or user.is_superuser
        or role in {"ADMIN", "IT_ADMIN", "LEADERSHIP"}
    )


@login_required
@user_passes_test(_is_schema_allowed)
def api_schema_ui(request):
    flags = get_effective_flags(request)
    allowed_roles = [str(r).upper() for r in flags.get("allowed_roles_api_schema", [])]
    if not flags.get("enable_api_schema_ui", True):
        return HttpResponseForbidden("API schema UI disabled by admin.")
    if allowed_roles:
        role = (getattr(request.user, "role", "") or "").upper()
        if role not in allowed_roles and not (
            request.user.is_staff or request.user.is_superuser
        ):
            return HttpResponseForbidden("You are not allowed to access API schema UI.")
    from django.urls import reverse

    return TemplateResponse(
        request, "api_schema_ui.html", {"schema_url": reverse("api-schema")}
    )


_schema_view_raw = cache_page(60)(
    get_schema_view(
        title="RunMyCampus API",
        description="Entity/analytics/session claims schema for frontend orchestration",
        version="1.0.0",
    )
)


@login_required
@user_passes_test(_is_schema_allowed)
def schema_view(request):
    return _schema_view_raw(request)


def admin_siteconfig_customizer_redirect(request):
    """Backward compatible: /admin/siteconfig/customizer/ → Studio OS Experience (align with platform)."""
    from django.urls import reverse

    return redirect(reverse("studio_os:experience"))


def legacy_siteconfig_customizer_redirect(request):
    """Phase B: /siteconfig/customizer/ → Studio OS Experience (tenant). Replaces old behavior path."""
    from django.urls import reverse

    return redirect(reverse("studio_os:experience"))


def legacy_workflow_hub_redirect(request):
    """Legacy /siteconfig/workflow-hub/ → Studio OS Automation (tenant)."""
    from django.urls import reverse

    url = reverse("studio_os:automation")
    if request.GET:
        url = f"{url}?{request.GET.urlencode()}"
    return redirect(url)


def legacy_report_library_redirect(request):
    """Legacy /siteconfig/reports/ or report-library → Output Studio · Report library pane (tenant)."""
    from django.urls import reverse
    from urllib.parse import urlencode

    base = reverse("studio_os:output")
    params = dict(request.GET.items())
    params.setdefault("pane", "reports")
    q = urlencode(params)
    return redirect(f"{base}?{q}" if q else base)


def school_surface_redirect(request, surface: str):
    destinations = {
        "apps": "/settings/app-catalog/",
        "imports": "/siteconfig/onboarding/",
        "billing": "/finance/",
        "money": "/finance/",
        "workflows": "/studio/automation/",
        "offline": "/portal/offline/sync-queue/",
        "audit": "/compliance/dashboard/",
        "security": "/compliance/dashboard/",
    }
    return redirect(destinations[surface])


def permission_denied(request, exception):
    is_admin_forbidden = (
        request.path.startswith("/admin")
        and request.user.is_authenticated
        and request.user.is_staff
        and not request.user.is_superuser
    )
    return render(
        request,
        "errors/403.html",
        {"is_admin_forbidden": is_admin_forbidden},
        status=403,
    )


def page_not_found(request, exception):
    from apps.schools.error_views import school_not_found

    return school_not_found(request)


def server_error(request):
    """Custom 500 (SOT batch 1218 hardened).

    Two-stage fallback so the 500 page survives context-processor or middleware
    crashes. Reference incident: `gilead-school.runmycampus.com/school/settings/`
    returning 500 with no operator-friendly recovery (2026-05-07).
    """
    context = {"user": getattr(request, "user", None)}
    try:
        return render(request, "errors/500.html", context, status=500)
    except Exception:
        from django.http import HttpResponse
        from django.template.loader import get_template
        try:
            html = get_template("errors/500_minimal.html").render({})
        except Exception:
            html = (
                "<!doctype html><meta charset=utf-8>"
                "<title>Service interrupted</title>"
                "<h1>500 - service interrupted</h1>"
                "<p>Retry once. If it persists, contact support.</p>"
                "<p><a href='/'>Home</a> &middot; <a href='/-/version/'>Version</a></p>"
            )
        return HttpResponse(html, status=500, content_type="text/html; charset=utf-8")


handler403 = permission_denied
handler404 = page_not_found
handler500 = server_error

urlpatterns = [
    path("", home, name="home"),
    path(
        "activation/first-action/",
        activation_first_action,
        name="activation_first_action",
    ),
    path("demo/flow/", demo_flow_index, name="demo_flow_index"),
    path("demo/flow/attendance/", demo_flow_attendance, name="demo_flow_attendance"),
    path(
        "demo/flow/attendance/complete/",
        demo_flow_attendance_complete,
        name="demo_flow_attendance_complete",
    ),
    path("demo/flow/marks/", demo_flow_marks, name="demo_flow_marks"),
    path(
        "demo/flow/marks/complete/",
        demo_flow_marks_complete,
        name="demo_flow_marks_complete",
    ),
    path("demo/flow/report/", demo_flow_report, name="demo_flow_report"),
    path(
        "demo/flow/report/complete/",
        demo_flow_report_complete,
        name="demo_flow_report_complete",
    ),
    path("demo/flow/complete/", demo_flow_complete, name="demo_flow_complete"),
    path("favicon.ico", favicon_redirect),
    # Before path("admin/", …) so legacy customizer hits Studio OS (Phase 5).
    path("admin/siteconfig/customizer/", admin_siteconfig_customizer_redirect),
    path("internal-admin/", internal_admin_alias_redirect, name="internal_admin"),
    path("internal-admin/<path:remaining>", internal_admin_alias_redirect),
    path("admin/", tenant_admin_site.urls),
    path("configuration/", tenant_configuration_forbidden, name="tenant_configuration_forbidden"),
    path("configuration/<path:remaining>", tenant_configuration_forbidden),
    path("school/settings/", school_configuration_center, name="school_configuration_center"),
    path("school/configuration/", school_configuration_center, name="school_configuration_center_canonical"),
    path("school/setup/blueprints/", tenant_blueprint_setup, name="tenant_blueprint_setup"),
    path("school/setup/packs/", tenant_pack_setup, name="tenant_pack_setup"),
    path("school/setup/imports/", school_surface_redirect, {"surface": "imports"}, name="school_setup_imports"),
    path("school/apps/", school_surface_redirect, {"surface": "apps"}, name="school_apps"),
    path("school/billing/", school_surface_redirect, {"surface": "billing"}, name="school_billing"),
    path("school/money/", school_surface_redirect, {"surface": "money"}, name="school_money"),
    path("school/workflows/", school_surface_redirect, {"surface": "workflows"}, name="school_workflows"),
    path("school/offline/", school_surface_redirect, {"surface": "offline"}, name="school_offline"),
    path("school/audit/", school_surface_redirect, {"surface": "audit"}, name="school_audit"),
    path("school/security/", school_surface_redirect, {"surface": "security"}, name="school_security"),
    path("api/schema/", schema_view, name="api-schema"),
    path("api/schema/ui/", api_schema_ui, name="api-schema-ui"),
    path(
        "backend/",
        lambda request: redirect("accounts:backend_dashboard", permanent=False),
    ),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("metrics/", obs_views.metrics, name="metrics"),
    path(
        "api/observability/copilot-metrics/",
        obs_views.copilot_metrics_json,
        name="copilot_metrics_json",
    ),
    path(
        "api/observability/slo-dashboard/",
        obs_views.api_operational_slo_dashboard,
        name="api_operational_slo_dashboard",
    ),
    path("admin/dashboard/", obs_views.admin_dashboard, name="admin_dashboard"),
    path("api/health/", obs_views.api_health, name="api_health"),
    path("api/admin/weather/", obs_views.api_admin_weather, name="api_admin_weather"),
    path(
        "api/weather/context/",
        obs_views.api_weather_context,
        name="api_weather_context",
    ),
    path("api/notifications/", obs_views.api_notifications, name="api_notifications"),
    path(
        "api/notifications/mark-all-read/",
        obs_views.api_notifications_mark_all_read,
        name="api_notifications_mark_all_read",
    ),
    path("api/activities/", obs_views.api_activities, name="api_activities"),
    path(
        "api/dashboard/charts/",
        obs_views.api_dashboard_charts,
        name="api_dashboard_charts",
    ),
    path("api/ai-copilot/validate/", ai_copilot_query, name="ai_copilot_query"),
    path("api/ai-copilot/permissions/", ai_permissions, name="ai_permissions"),
    path("api/ai-copilot/limits/", ai_copilot_limits, name="ai_copilot_limits"),
    path("api/ai-copilot/config/", ai_copilot_config, name="ai_copilot_config"),
    path("api/ai-copilot/audit/", ai_copilot_audit_feed, name="ai_copilot_audit"),
    path("siteconfig/customizer/", legacy_siteconfig_customizer_redirect),
    path("siteconfig/workflow-hub/", legacy_workflow_hub_redirect),
    path("siteconfig/report-library/", legacy_report_library_redirect),
    path("siteconfig/reports/", legacy_report_library_redirect),
    path(
        "studio/", include(("apps.studio_os.urls", "studio_os"), namespace="studio_os")
    ),
    path(
        "verify/<str:token>/",
        __import__(
            "apps.siteconfig.views_verify", fromlist=["verify_student_id"]
        ).verify_student_id,
        name="verify_student_id",
    ),
    path("api/", include(("apps.api.urls", "api"), namespace="api")),
    path("api/v1/", include(("apps.api.urls_v1", "api_v1"), namespace="api_v1")),
    path(
        "siteconfig/school-configuration/",
        school_configuration_center,
        name="siteconfig_school_configuration",
    ),
    path(
        "siteconfig/",
        include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig"),
    ),
    path("marketplace/", include("apps.marketplace.tenant_urls")),
    path(
        "api/internal/click-tracking/",
        record_click_event,
        name="record_click_event",
    ),
    path(
        "internal/click-measurement/",
        click_measurement_dashboard,
        name="click_measurement_dashboard",
    ),
    path(
        "settings/installed-apps/",
        login_required(tenant_installed_apps),
        name="tenant_installed_apps",
    ),
    path(
        "settings/app-catalog/",
        login_required(tenant_app_catalog),
        name="tenant_app_catalog",
    ),
    path(
        "settings/install-impact-preview/",
        login_required(tenant_install_impact_preview),
        name="tenant_install_impact_preview",
    ),
    path(
        "settings/install-app/",
        login_required(tenant_install_app),
        name="tenant_install_app",
    ),
    path(
        "settings/uninstall-app/",
        login_required(tenant_uninstall_app),
        name="tenant_uninstall_app",
    ),
    path(
        "settings/save-installation-config/",
        login_required(tenant_save_installation_config),
        name="tenant_save_installation_config",
    ),
    path(
        "settings/scope-consent/",
        login_required(tenant_scope_consent),
        name="tenant_scope_consent",
    ),
    path(
        "settings/approve-scope/",
        login_required(tenant_approve_scope),
        name="tenant_approve_scope",
    ),
    path(
        "settings/activate-installation/",
        login_required(tenant_activate_installation),
        name="tenant_activate_installation",
    ),
    path(
        "api-center/",
        include(("apps.apicenter.urls", "apicenter"), namespace="apicenter"),
    ),
    path(
        "domain-events/",
        include(("apps.events.urls", "events"), namespace="events"),
    ),
    path(
        "automation/",
        include(("apps.automation.urls", "automation"), namespace="automation"),
    ),
    path(
        "authentication/",
        include(("apps.accounts.urls", "accounts"), namespace="accounts"),
    ),
    path("evals/", include(("apps.evals.urls", "evals"), namespace="evals")),
    path(
        "academics/",
        include(("apps.academics.urls", "academics"), namespace="academics"),
    ),
    path("portal/", include(("apps.portal.urls", "portal"), namespace="portal")),
    path("portal", lambda request: redirect("portal:parent_dashboard")),
    path(
        "events/",
        include(
            ("apps.school_events.urls", "school_events"), namespace="school_events"
        ),
    ),
    path("kb/", include(("apps.portal.urls_kb", "kb"), namespace="kb")),
    path("reports/", include(("apps.reports.urls", "reports"), namespace="reports")),
    path(
        "analytics/",
        include(("apps.analytics.urls", "analytics"), namespace="analytics"),
    ),
    path(
        "platform-runtime/",
        include(
            ("apps.platform_runtime.urls", "platform_runtime"),
            namespace="platform_runtime",
        ),
    ),
    path("finance/", include(("apps.finance.urls", "finance"), namespace="finance")),
    path("payroll/", include(("apps.payroll.urls", "payroll"), namespace="payroll")),
    path(
        "compliance/",
        include(("apps.compliance.urls", "compliance"), namespace="compliance"),
    ),
    path(
        "communication/",
        include(
            ("apps.communication.urls", "communication"), namespace="communication"
        ),
    ),
    path("emis/", include(("emis.urls", "emis"), namespace="emis")),
    path(
        "requests/", include(("apps.requests.urls", "requests"), namespace="requests")
    ),
    path(
        "organization/network/",
        parent_tenant_dashboard,
        name="organization_network_dashboard",
    ),
    path(
        "api/tenant/domains/",
        api_domains_list_or_create,
        name="api_domains_list_or_create",
    ),
    path(
        "api/tenant/domains/<uuid:school_domain_id>/verify/",
        api_domains_verify,
        name="api_domains_verify",
    ),
    path("account-frozen/", frozen_account, name="account_frozen"),
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
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
