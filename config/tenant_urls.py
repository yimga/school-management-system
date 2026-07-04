"""
Tenant (school app) URL configuration for subdomain or /t/<slug>/.
Used when request.urlconf is set to this module by UrlConfSwitcherMiddleware.
"""

from django.conf import settings
from django.conf.urls.static import static as static_media_serve
from django.contrib.staticfiles.storage import staticfiles_storage
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
    ai_health,
)
from apps.portal.views_configure import portal_configure_hub
from apps.siteconfig.views_school_help_ai import school_help_ai
from apps.schools.views_pending_provision import api_public_pending_provision_progress
from apps.schools.views_school_readiness import api_school_readiness
from apps.academics.views_discipline_api import api_discipline_incidents
from apps.lifecycle.views_tenant_lifecycle import (
    api_tenant_launch_rail,
    api_tenant_lifecycle_hub,
    api_tenant_provisioning_status,
    tenant_launch_fast_path,
    tenant_lifecycle_command_center,
    tenant_provisioning_status,
)
from apps.siteconfig.views_tenant_studio_hub import (
    school_studio_hub,
    school_studio_redirect_help,
    school_studio_redirect_launch,
    school_studio_redirect_migration,
    school_studio_redirect_setup,
)
from apps.schools.views_tenant_self_offboarding import (
    api_tenant_offboarding_cancel,
    api_tenant_offboarding_export,
    api_tenant_offboarding_export_download,
    api_tenant_offboarding_request_closure,
    api_tenant_offboarding_snapshot,
    tenant_offboarding_page,
)
from config.admin import tenant_admin_site
from apps.schools.activation_views import (
    ACTIVATION_FIRST_ACTION_PATH,
    ACTIVATION_FIRST_ACTION_URL_NAME,
    activation_first_action,
)
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
    tenant_import_setup,
    tenant_pack_setup,
)


def home(request):
    if request.user.is_authenticated:
        return redirect("accounts:redirect")
    return redirect("accounts:login")


def favicon_redirect(request):
    """Serve favicon by redirecting to default static icon; avoids 500 when 404 pipeline runs for /favicon.ico."""
    return redirect(
        staticfiles_storage.url("images/runmycampus-icon.png"),
        permanent=False,
    )


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
    # A miss under /static/ or /media/ (e.g. a browser-requested *.css.map source
    # map that isn't shipped) must NOT render the branded tenant 404 template:
    # that pulls tenant context + context processors that can raise on an asset
    # path, turning the 404 into a 500. Return a plain 404 for asset paths — the
    # same reason favicon_redirect exists. Real page 404s still get the brand page.
    path = request.path or ""
    static_url = settings.STATIC_URL or "/static/"
    media_url = settings.MEDIA_URL or "/media/"
    if path.startswith(static_url) or path.startswith(media_url):
        from django.http import HttpResponseNotFound

        return HttpResponseNotFound("Not found")

    from apps.schools.error_views import school_not_found

    return school_not_found(request)


def server_error(request):
    """Custom 500 (SOT batch 1218 hardened).

    Two-stage fallback so the 500 page survives context-processor or middleware
    crashes. Reference incident: `example-school.runmycampus.com/school/settings/`
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

from config.error_handlers import service_unavailable as handler503  # noqa: E402

from apps.siteconfig.command_bar_registry import CommandBarActionsView  # noqa: E402
from apps.siteconfig.views_manifest import (  # noqa: E402
    platform_manifest as _platform_manifest,
    portal_manifest as _portal_manifest,
)
from apps.siteconfig.views_manifest_icon import (  # noqa: E402
    icon_any as _manifest_icon_any,
    icon_maskable as _manifest_icon_maskable,
)
from apps.siteconfig.views_service_worker import (  # noqa: E402
    service_worker_asset_manifest,
    service_worker_reset,
    service_worker_script,
)

urlpatterns = [
    # Language switcher (Django i18n) — must exist on every host urlconf or the
    # platform-wide "Translate this page" form + error-page links raise NoReverseMatch.
    path("i18n/setlang/", __import__("django.views.i18n", fromlist=["set_language"]).set_language, name="set_language"),
    # Persisting wrapper: writes the choice to User.preferred_language (durable /
    # cross-device) in addition to the session + cookie. The tenant portal
    # language switcher posts here; must be mounted on the tenant host too.
    path(
        "i18n/setlang/persist/",
        __import__("apps.accounts.views_i18n", fromlist=["set_language_persist"]).set_language_persist,
        name="set_language_persist",
    ),
    path("", home, name="home"),
    # Universal command bar (v3.53.0): mirror of config.urls / config.manager_urls
    # path so the cmd+k overlay loaded into every tenant-host shell can reverse the
    # action-registry endpoint. # rbac-allow: command-bar-server-filters-actions-per-user-and-tenant
    path("api/command-bar/actions/", CommandBarActionsView.as_view(), name="command_bar_actions"),
    path(
        ACTIVATION_FIRST_ACTION_PATH.lstrip("/"),
        activation_first_action,
        name=ACTIVATION_FIRST_ACTION_URL_NAME,
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
    path("sw.js", service_worker_script, name="service_worker_root"),
    # One-click escape hatch for a browser stuck on a stale service worker. MUST
    # exist on the tenant urlconf — a tenant subdomain resolves through this
    # module, so without it /sw-reset/ 404s exactly where a stuck cache-first
    # worker is serving days-old HTML (the "deploys never show up" report).
    path("sw-reset/", service_worker_reset, name="service_worker_reset"),
    path(
        "sw-asset-manifest.json",
        service_worker_asset_manifest,
        name="sw_asset_manifest",
    ),
    path("manifest.json", _platform_manifest, name="pwa_manifest_platform"),
    path("manifest-portal.json", _portal_manifest, name="pwa_manifest_portal"),
    path(
        "manifest/icon-<int:size>.png",
        _manifest_icon_any,
        name="pwa_manifest_icon_any",
    ),
    path(
        "manifest/icon-<int:size>-maskable.png",
        _manifest_icon_maskable,
        name="pwa_manifest_icon_maskable",
    ),
    path("internal-admin/", internal_admin_alias_redirect, name="internal_admin"),
    path("internal-admin/<path:remaining>", internal_admin_alias_redirect),
    path("admin/", tenant_admin_site.urls),
    path("configuration/", school_configuration_center, name="tenant_configuration_center"),
    path("configuration/<path:remaining>", school_configuration_center),
    path("school/settings/", school_configuration_center, name="school_configuration_center"),
    path("school/configuration/", school_configuration_center, name="school_configuration_center_canonical"),
    path("school/setup/blueprints/", tenant_blueprint_setup, name="tenant_blueprint_setup"),
    path("school/setup/packs/", tenant_pack_setup, name="tenant_pack_setup"),
    path("school/setup/imports/", tenant_import_setup, name="school_setup_imports"),
    path(
        "school/setup/migration-cloud/",
        include(
            ("apps.migration_cloud.urls_connectors", "migration_cloud_connector"),
            namespace="migration_cloud_connector",
        ),
    ),
    path("school/apps/", school_surface_redirect, {"surface": "apps"}, name="school_apps"),
    path("school/billing/", school_surface_redirect, {"surface": "billing"}, name="school_billing"),
    path("school/money/", school_surface_redirect, {"surface": "money"}, name="school_money"),
    path("school/workflows/", school_surface_redirect, {"surface": "workflows"}, name="school_workflows"),
    path("school/offline/", school_surface_redirect, {"surface": "offline"}, name="school_offline"),
    path("school/audit/", school_surface_redirect, {"surface": "audit"}, name="school_audit"),
    path("school/security/", school_surface_redirect, {"surface": "security"}, name="school_security"),
    path("school/help/ai/", school_help_ai, name="school_help_ai"),
    path("school/studio/", school_studio_hub, name="school_studio"),
    path(
        "school/studio/provisioning/",
        tenant_provisioning_status,
        name="tenant_provisioning_status",
    ),
    path(
        "school/studio/fast-path/",
        tenant_launch_fast_path,
        name="tenant_launch_fast_path",
    ),
    path(
        "school/studio/lifecycle/",
        tenant_lifecycle_command_center,
        name="tenant_lifecycle_command_center",
    ),
    path(
        "api/school/lifecycle/provisioning/",
        api_tenant_provisioning_status,
        name="api_tenant_provisioning_status",
    ),
    path(
        "api/pending-provision/progress/",
        api_public_pending_provision_progress,
        name="api_public_pending_provision_progress",
    ),
    path(
        "api/school/lifecycle/launch-rail/",
        api_tenant_launch_rail,
        name="api_tenant_launch_rail",
    ),
    path(
        "api/school/lifecycle/hub/",
        api_tenant_lifecycle_hub,
        name="api_tenant_lifecycle_hub",
    ),
    path(
        "api/school/readiness/",
        api_school_readiness,
        name="api_school_readiness",
    ),
    path(
        "api/discipline/incidents/",
        api_discipline_incidents,
        name="api_discipline_incidents",
    ),
    path("school/studio/setup/", school_studio_redirect_setup, name="school_studio_setup"),
    path("school/studio/readiness/", school_studio_hub, name="school_studio_readiness"),
    path("school/studio/migration/", school_studio_redirect_migration, name="school_studio_migration"),
    path("school/studio/help/", school_studio_redirect_help, name="school_studio_help"),
    path("school/studio/launch/", school_studio_redirect_launch, name="school_studio_launch"),
    path("school/studio/offboarding/", tenant_offboarding_page, name="tenant_offboarding"),
    path(
        "school/studio/templates/",
        include(("apps.brand_experience.urls_template_marketplace", "template_marketplace"), namespace="template_marketplace"),
    ),
    path(
        "school/studio/infrastructure/email/",
        __import__(
            "apps.schools.views_infrastructure",
            fromlist=["infrastructure_email_page"],
        ).infrastructure_email_page,
        name="school_studio_infrastructure_email",
    ),
    path(
        "school/studio/infrastructure/email/save/",
        __import__(
            "apps.schools.views_infrastructure",
            fromlist=["infrastructure_email_save"],
        ).infrastructure_email_save,
        name="school_studio_infrastructure_email_save",
    ),
    path(
        "school/studio/infrastructure/email/probe/",
        __import__(
            "apps.schools.views_infrastructure",
            fromlist=["infrastructure_email_probe"],
        ).infrastructure_email_probe,
        name="school_studio_infrastructure_email_probe",
    ),
    path(
        "school/studio/infrastructure/offline/",
        __import__(
            "apps.schools.views_infrastructure",
            fromlist=["infrastructure_offline_page"],
        ).infrastructure_offline_page,
        name="school_studio_infrastructure_offline",
    ),
    path(
        "school/studio/infrastructure/offline/save/",
        __import__(
            "apps.schools.views_infrastructure",
            fromlist=["infrastructure_offline_save"],
        ).infrastructure_offline_save,
        name="school_studio_infrastructure_offline_save",
    ),
    # Wave L4 (v3.61.3 — 2026-05-22): one-click DSAR export + close (lifecycle app).
    path(
        "portal/configure/offboarding/export-and-close/",
        __import__("apps.lifecycle.views_dsar", fromlist=["dsar_export_and_close"]).dsar_export_and_close,
        name="lifecycle_dsar_export_and_close",
    ),
    path(
        "portal/configure/privacy/data-export/",
        __import__(
            "apps.lifecycle.views_tenant_gdpr_export",
            fromlist=["tenant_gdpr_data_export"],
        ).tenant_gdpr_data_export,
        name="tenant_gdpr_data_export",
    ),
    # Wave L5 (v3.61.4 — 2026-05-22): public per-tenant migration status (lifecycle app).
    path(
        "portal/migration/status/",
        __import__("apps.lifecycle.views_migration_status", fromlist=["tenant_migration_status"]).tenant_migration_status,
        name="lifecycle_migration_status",
    ),
    path(
        "api/school/offboarding/",
        api_tenant_offboarding_snapshot,
        name="tenant_offboarding_snapshot",
    ),
    path(
        "api/school/offboarding/export/",
        api_tenant_offboarding_export,
        name="tenant_offboarding_export",
    ),
    path(
        "api/school/offboarding/export/download/",
        api_tenant_offboarding_export_download,
        name="tenant_offboarding_export_download",
    ),
    path(
        "api/school/offboarding/request-closure/",
        api_tenant_offboarding_request_closure,
        name="tenant_offboarding_request",
    ),
    path(
        "api/school/offboarding/cancel/",
        api_tenant_offboarding_cancel,
        name="tenant_offboarding_cancel",
    ),
    path("api/schema/", schema_view, name="api-schema"),
    path("api/schema/ui/", api_schema_ui, name="api-schema-ui"),
    path(
        "backend/",
        lambda request: redirect("accounts:backend_dashboard", permanent=False),
    ),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("-/version/", obs_views.public_version, name="public_version"),
    path("api/system/version/", obs_views.public_version, name="api_system_version"),
    path("version.json", obs_views.public_version, name="public_version_json"),
    path("status/", obs_views.public_status, name="status"),
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
    path("api/ai/health/", ai_health, name="ai_health"),
    path(
        "studio/", include(("apps.studio_os.urls", "studio_os"), namespace="studio_os")
    ),
    # Unified Wizard Engine (setup_studio) — its urlconf carries its own
    # ``school/studio/wizards/...`` prefixes and is DESIGNED to mount at the
    # tenant root (see apps/setup_studio/urls.py docstring). Without this the
    # ``setup_studio`` namespace is absent on tenant hosts, so every
    # ``reverse("setup_studio:tenant_wizard…")`` (e.g. the post-MFA / onboarding
    # legacy_view_bridge redirects) silently fails and the whole engine falls
    # back to legacy flows. Registering it here makes the wizards reachable AND
    # the reverses resolve on the tenant subdomain.
    path("", include(("apps.setup_studio.urls", "setup_studio"), namespace="setup_studio")),
    path(
        "verify/<str:token>/",
        __import__(
            "apps.siteconfig.views_verify", fromlist=["verify_student_id"]
        ).verify_student_id,
        name="verify_student_id",
    ),
    path("api/", include(("apps.api.urls", "api"), namespace="api")),
    path("api/v1/", include(("apps.api.urls_v1", "api_v1"), namespace="api_v1")),
    # v4.02.13: assist-dock client endpoints on the tenant host (portal + tenant
    # admin render the dock) so dock actions are not silently dead.
    path(
        "assist-dock/",
        include(("apps.assist_dock.urls", "assist_dock"), namespace="assist_dock"),
    ),
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
    path(
        "portal/console/",
        lambda request: redirect("accounts:backend_dashboard"),
        name="portal_console",
    ),
    path(
        "portal/configure/",
        portal_configure_hub,
        name="portal_configure",
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
    path("", include(("apps.feedback.tenant_urls", "feedback"), namespace="feedback")),
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
    urlpatterns += static_media_serve(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
