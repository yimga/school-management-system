from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path, reverse
from django.views.i18n import set_language
from django.views.decorators.cache import cache_page
from rest_framework.schemas import get_schema_view
from django.contrib.auth.decorators import login_required, user_passes_test
from django.template.response import TemplateResponse
from django.http import HttpResponseForbidden

from apps.platform_runtime.helpers import get_effective_flags
from apps.platform_runtime.views_rum import rum_ingest

from apps.observability import views as obs_views
from apps.portal.views_ai_copilot import (
    ai_copilot_query,
    ai_permissions,
    ai_copilot_limits,
    ai_copilot_config,
    ai_copilot_audit_feed,
)
from config.admin import platform_admin_site
from apps.schools.marketing_views import (
    marketing_landing,
    regional_marketing_landing,
    marketing_page,
    topical_marketing_landing,
    blog_post_detail,
    buyer_toolkit_download,
    marketing_funnel_dashboard,
    marketing_robots_txt,
    marketing_sitemap_xml,
    developer_public_api_docs,
    migrate_marketing_page,
    institution_marketing_page,
    role_marketing_page,
)
from apps.schools.signup_views import (
    signup_school,
    verify_signup,
    api_trial_school,
    onboarding_wizard,
)
from apps.schools.section8_views import (
    verify_caddy_domain,
    global_login_discovery,
    find_school,
    public_verify_hub,
    public_support_hub,
    lti_launch,
    lti_launch_callback,
    lti_ags_lineitems,
    lti_ags_lineitem_detail,
    lti_ags_scores,
    lti_ags_results,
    lti_nrps_memberships,
    lti_deep_linking,
    jwks_json,
    frozen_account,
)
from apps.schools.parent_tenant_views import parent_tenant_dashboard


def home(request):
    # Authenticated users go to their backend/dashboard
    if request.user.is_authenticated:
        return redirect("accounts:redirect")
    # Base/public host (runmycampus.com): public marketing landing, not login
    from apps.schools.tenant_url import is_base_domain

    if is_base_domain(request):
        return redirect("marketing_landing")
    return redirect("accounts:login")


def offline_page(request):
    """Offline fallback shell served by service-worker navigation fallback."""
    return render(request, "offline.html", status=200)


def _coerce_request_user_for_error_pages(request):
    """
    Error views may run without AuthenticationMiddleware; tests may set user=None.
    Auth context processor always supplies ``user`` from request.user — ensure it is never None
    so base templates can safely reference user.username (AnonymousUser uses empty string).
    """
    from django.contrib.auth.models import AnonymousUser

    if getattr(request, "user", None) is None:
        request.user = AnonymousUser()


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
    """Render Redoc/Swagger-lite page for API schema (admin-only)."""
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
    return TemplateResponse(
        request,
        "api_schema_ui.html",
        {
            "schema_url": reverse("api-schema"),
        },
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
    """API schema (JSON) – same access as schema UI."""
    return _schema_view_raw(request)


def admin_siteconfig_customizer_redirect(request):
    """Backward compatible URL: /admin/siteconfig/customizer/ → Studio Experience."""
    return redirect(reverse("studio_os:experience"))


def legacy_workflow_hub_redirect(request):
    """Step 6 / Optional 12: Legacy workflow hub → Studio OS Automation. When product confirms a different path, add it here or replace this path."""
    return redirect(reverse("studio_os:automation"))


def legacy_report_library_redirect(request):
    """Legacy report library URLs → Output Studio · Report library pane (§4.4 / §6.1)."""
    from urllib.parse import urlencode

    base = reverse("studio_os:output")
    params = dict(request.GET.items())
    params.setdefault("pane", "reports")
    q = urlencode(params)
    return redirect(f"{base}?{q}" if q else base)


def legacy_siteconfig_customizer_redirect(request):
    """Phase B: /siteconfig/customizer/ → Studio OS Experience. Replaces old behavior path (manager and tenant)."""
    return redirect(reverse("studio_os:experience"))


def permission_denied(request, exception):
    """Custom 403: friendly message when staff hit Admin without superuser."""
    _coerce_request_user_for_error_pages(request)
    is_admin_forbidden = (
        request.path.startswith("/admin")
        and request.user.is_authenticated
        and request.user.is_staff
        and not request.user.is_superuser
    )
    template = (
        "errors/403_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/403.html"
    )
    return render(
        request, template, {"is_admin_forbidden": is_admin_forbidden}, status=403
    )


def page_not_found(request, exception):
    """Custom 404 page."""
    _coerce_request_user_for_error_pages(request)
    template = (
        "errors/404_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/404.html"
    )
    return render(request, template, status=404)


def server_error(request):
    """Custom 500 page. Pass user so base template and includes render when context processors failed."""
    _coerce_request_user_for_error_pages(request)
    context = {"user": request.user}
    template = (
        "errors/500_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/500.html"
    )
    return render(request, template, context, status=500)


handler403 = permission_denied
handler404 = page_not_found
handler500 = server_error

urlpatterns = [
    path("", home, name="home"),
    path("offline/", offline_page, name="offline"),
    # Language switcher (Django i18n; POST language then redirect)
    path("i18n/setlang/", set_language, name="set_language"),
    # Must be before path("admin/", ...) so the redirect runs (Phase 5 / Studio OS spine).
    path("admin/siteconfig/customizer/", admin_siteconfig_customizer_redirect),
    # Admin interfaces - /admin/ only for superuser/staff
    path("admin/", platform_admin_site.urls),
    # API schema (RBAC-protected; same as schema UI)
    path("api/schema/", schema_view, name="api-schema"),
    path("api/schema/ui/", api_schema_ui, name="api-schema-ui"),
    # Part F 16.3: GraphQL gateway
    path(
        "graphql/",
        __import__("config.graphql_view", fromlist=["graphql_gateway"]).graphql_gateway,
        name="graphql",
    ),
    # Frontend admin dashboard - separate from /admin/ (redirect to canonical URL)
    path(
        "backend/",
        lambda request: redirect("accounts:backend_dashboard", permanent=False),
    ),
    # Health and metrics
    path("healthz/", obs_views.healthz, name="healthz"),
    # Public health endpoint for load balancers
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
    path(
        "api/observability/runtime-inspect/",
        obs_views.runtime_inspect,
        name="runtime_inspect",
    ),
    # Legacy alias: /admin/dashboard/ resolves to canonical /admin/
    path("admin/dashboard/", obs_views.admin_dashboard, name="admin_dashboard"),
    # API endpoints for admin dashboard
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
    # Phase 3 API endpoints
    path("api/activities/", obs_views.api_activities, name="api_activities"),
    path(
        "api/dashboard/charts/",
        obs_views.api_dashboard_charts,
        name="api_dashboard_charts",
    ),
    # AI Copilot API endpoints (RBAC Protected)
    path("api/ai-copilot/validate/", ai_copilot_query, name="ai_copilot_query"),
    path("api/ai-copilot/permissions/", ai_permissions, name="ai_permissions"),
    path("api/ai-copilot/limits/", ai_copilot_limits, name="ai_copilot_limits"),
    path("api/ai-copilot/config/", ai_copilot_config, name="ai_copilot_config"),
    path("api/ai-copilot/audit/", ai_copilot_audit_feed, name="ai_copilot_audit"),
    # Step 6 / Phase B: Legacy siteconfig paths → Studio OS (product-confirmed paths)
    path("siteconfig/customizer/", legacy_siteconfig_customizer_redirect),
    path("siteconfig/workflow-hub/", legacy_workflow_hub_redirect),
    path("siteconfig/report-library/", legacy_report_library_redirect),
    path("siteconfig/reports/", legacy_report_library_redirect),
    # API Routes
    path(
        "verify/<str:token>/",
        __import__(
            "apps.siteconfig.views_verify", fromlist=["verify_student_id"]
        ).verify_student_id,
        name="verify_student_id",
    ),
    path("api/", include(("apps.api.urls", "api"), namespace="api")),
    path("api/v1/", include(("apps.api.urls_v1", "api_v1"), namespace="api_v1")),
    # Apps
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
    path("kb/", include(("apps.portal.urls_kb", "kb"), namespace="kb")),
    path("reports/", include(("apps.reports.urls", "reports"), namespace="reports")),
    path(
        "analytics/",
        include(("apps.analytics.urls", "analytics"), namespace="analytics"),
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
    # Super Admin (multi-tenant provisioning)
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    # §3.3 Metadata search (staff-only)
    path(
        "api/internal/metadata/",
        include(("apps.metadata.urls", "metadata"), namespace="metadata"),
    ),
    path("api/internal/rum/", rum_ingest, name="rum_ingest"),
    # Section 8: Caddy on-demand TLS ask (no auth; restrict by IP in production)
    path("api/caddy-check/", verify_caddy_domain),
    path("api/v1/auth/check-domain/", verify_caddy_domain),
    path("discover/", global_login_discovery, name="global_login_discovery"),
    path("find/", find_school, name="find_school"),
    path("verify/", public_verify_hub, name="public_verify_hub"),
    path("support/", public_support_hub, name="public_support_hub"),
    path("robots.txt", marketing_robots_txt, name="marketing_robots_txt"),
    path("sitemap.xml", marketing_sitemap_xml, name="marketing_sitemap_xml"),
    path("marketing/", marketing_landing, name="marketing_landing"),
    path(
        "education-operating-system/",
        marketing_page,
        {"page_slug": "education-operating-system"},
        name="marketing_education_operating_system",
    ),
    path(
        "platform/",
        marketing_page,
        {"page_slug": "platform"},
        name="marketing_platform",
    ),
    path(
        "platform/education-os/",
        marketing_page,
        {"page_slug": "platform-education-os"},
        name="marketing_platform_education_os",
    ),
    path(
        "platform/control-plane/",
        marketing_page,
        {"page_slug": "platform-control-plane"},
        name="marketing_platform_control_plane",
    ),
    path(
        "platform/marketplace/",
        marketing_page,
        {"page_slug": "platform-marketplace"},
        name="marketing_platform_marketplace",
    ),
    path(
        "platform/migration-cloud/",
        marketing_page,
        {"page_slug": "platform-migration-cloud"},
        name="marketing_platform_migration_cloud",
    ),
    path(
        "platform/runtime/",
        marketing_page,
        {"page_slug": "platform-runtime"},
        name="marketing_platform_runtime",
    ),
    path(
        "platform/integrations/",
        marketing_page,
        {"page_slug": "platform-integrations"},
        name="marketing_platform_integrations",
    ),
    path(
        "platform/security/",
        marketing_page,
        {"page_slug": "platform-security"},
        name="marketing_platform_security",
    ),
    path(
        "platform/analytics/",
        marketing_page,
        {"page_slug": "platform-analytics"},
        name="marketing_platform_analytics",
    ),
    path(
        "product/", marketing_page, {"page_slug": "product"}, name="marketing_product"
    ),
    path(
        "products/admissions/",
        marketing_page,
        {"page_slug": "products-admissions"},
        name="marketing_products_admissions",
    ),
    path(
        "products/academics/",
        marketing_page,
        {"page_slug": "products-academics"},
        name="marketing_products_academics",
    ),
    path(
        "products/finance/",
        marketing_page,
        {"page_slug": "products-finance"},
        name="marketing_products_finance",
    ),
    path(
        "products/communication/",
        marketing_page,
        {"page_slug": "products-communication"},
        name="marketing_products_communication",
    ),
    path(
        "products/automation/",
        marketing_page,
        {"page_slug": "products-automation"},
        name="marketing_products_automation",
    ),
    path(
        "products/analytics/",
        marketing_page,
        {"page_slug": "products-analytics"},
        name="marketing_products_analytics",
    ),
    path(
        "solutions/",
        marketing_page,
        {"page_slug": "solutions"},
        name="marketing_solutions",
    ),
    path(
        "solutions/k12/",
        institution_marketing_page,
        {"institution_slug": "k12"},
        name="institution_k12",
    ),
    path(
        "solutions/universities/",
        institution_marketing_page,
        {"institution_slug": "universities"},
        name="institution_universities",
    ),
    path(
        "solutions/technical-schools/",
        institution_marketing_page,
        {"institution_slug": "technical-schools"},
        name="institution_technical_schools",
    ),
    path(
        "solutions/private-schools/",
        institution_marketing_page,
        {"institution_slug": "private-schools"},
        name="institution_private_schools",
    ),
    path(
        "solutions/government-education/",
        institution_marketing_page,
        {"institution_slug": "government-education"},
        name="institution_government_education",
    ),
    path(
        "roles/school-admin/",
        role_marketing_page,
        {"role_slug": "school-admin"},
        name="role_school_admin",
    ),
    path(
        "roles/teachers/",
        role_marketing_page,
        {"role_slug": "teachers"},
        name="role_teachers",
    ),
    path(
        "roles/parents/",
        role_marketing_page,
        {"role_slug": "parents"},
        name="role_parents",
    ),
    path(
        "roles/students/",
        role_marketing_page,
        {"role_slug": "students"},
        name="role_students",
    ),
    path(
        "roles/it-directors/",
        role_marketing_page,
        {"role_slug": "it-directors"},
        name="role_it_directors",
    ),
    path(
        "roles/government/",
        role_marketing_page,
        {"role_slug": "government"},
        name="role_government",
    ),
    path(
        "pricing/", marketing_page, {"page_slug": "pricing"}, name="marketing_pricing"
    ),
    path(
        "compare/", marketing_page, {"page_slug": "compare"}, name="marketing_compare"
    ),
    path(
        "case-studies/",
        marketing_page,
        {"page_slug": "case-studies"},
        name="marketing_case_studies",
    ),
    path(
        "customers/",
        lambda req: redirect("marketing_case_studies", permanent=False),
        name="marketing_customers",
    ),
    path(
        "security-compliance/",
        marketing_page,
        {"page_slug": "security-compliance"},
        name="marketing_security_compliance",
    ),
    path(
        "integrations/",
        marketing_page,
        {"page_slug": "integrations"},
        name="marketing_integrations",
    ),
    path(
        "book-demo/",
        marketing_page,
        {"page_slug": "book-demo"},
        name="marketing_book_demo",
    ),
    path(
        "interactive-preview/",
        marketing_page,
        {"page_slug": "interactive-preview"},
        name="marketing_interactive_preview",
    ),
    path(
        "product-tour/",
        marketing_page,
        {"page_slug": "interactive-preview"},
        name="marketing_product_tour",
    ),
    path(
        "getting-started/",
        marketing_page,
        {"page_slug": "getting-started"},
        name="marketing_getting_started",
    ),
    path("themes/", marketing_page, {"page_slug": "themes"}, name="marketing_themes"),
    path(
        "design-studio/",
        marketing_page,
        {"page_slug": "design-studio"},
        name="marketing_design_studio",
    ),
    path("uptime/", marketing_page, {"page_slug": "uptime"}, name="marketing_uptime"),
    path(
        "buyer-toolkit/",
        marketing_page,
        {"page_slug": "buyer-toolkit"},
        name="marketing_buyer_toolkit",
    ),
    path(
        "buyer-toolkit/download/<str:document>/",
        buyer_toolkit_download,
        name="marketing_buyer_toolkit_download",
    ),
    path(
        "funnel-dashboard/",
        marketing_funnel_dashboard,
        name="marketing_funnel_dashboard",
    ),
    path("about/", marketing_page, {"page_slug": "about"}, name="marketing_about"),
    path(
        "features/",
        marketing_page,
        {"page_slug": "features"},
        name="marketing_features",
    ),
    path("blog/", marketing_page, {"page_slug": "blog"}, name="marketing_blog"),
    path("blog/<slug:slug>/", blog_post_detail, name="marketing_blog_detail"),
    path(
        "contact/", marketing_page, {"page_slug": "contact"}, name="marketing_contact"
    ),
    path(
        "why-switch/",
        marketing_page,
        {"page_slug": "why-switch"},
        name="marketing_why_switch",
    ),
    path(
        "school-management-system/",
        marketing_page,
        {"page_slug": "school-management-system"},
        name="marketing_school_management_system",
    ),
    path(
        "student-information-system/",
        marketing_page,
        {"page_slug": "student-information-system"},
        name="marketing_student_information_system",
    ),
    path(
        "education-erp/",
        marketing_page,
        {"page_slug": "education-erp"},
        name="marketing_education_erp",
    ),
    path(
        "school-administration-software/",
        marketing_page,
        {"page_slug": "school-administration-software"},
        name="marketing_school_administration_software",
    ),
    path(
        "10-reasons/",
        marketing_page,
        {"page_slug": "10-reasons"},
        name="marketing_10_reasons",
    ),
    path(
        "resources/",
        marketing_page,
        {"page_slug": "resources"},
        name="marketing_resources",
    ),
    path(
        "research/",
        marketing_page,
        {"page_slug": "research"},
        name="marketing_research",
    ),
    path(
        "reports/", marketing_page, {"page_slug": "reports"}, name="marketing_reports"
    ),
    path("guides/", marketing_page, {"page_slug": "guides"}, name="marketing_guides"),
    path("events/", marketing_page, {"page_slug": "events"}, name="marketing_events"),
    path(
        "trust-center/",
        marketing_page,
        {"page_slug": "trust-center"},
        name="marketing_trust_center",
    ),
    path(
        "trust-center/ferpa/",
        marketing_page,
        {"page_slug": "trust-center-ferpa"},
        name="marketing_trust_ferpa",
    ),
    path(
        "trust-center/gdpr/",
        marketing_page,
        {"page_slug": "trust-center-gdpr"},
        name="marketing_trust_gdpr",
    ),
    path(
        "trust-center/retention/",
        marketing_page,
        {"page_slug": "trust-center-retention"},
        name="marketing_trust_retention",
    ),
    path(
        "trust-center/incidents/",
        marketing_page,
        {"page_slug": "trust-center-breach"},
        name="marketing_trust_incidents",
    ),
    path(
        "compare/replacement/",
        marketing_page,
        {"page_slug": "compare-replacement"},
        name="marketing_compare_replacement",
    ),
    path(
        "developers/",
        marketing_page,
        {"page_slug": "developers"},
        name="marketing_developers",
    ),
    path(
        "developers/api-docs/",
        developer_public_api_docs,
        name="developer_public_api_docs",
    ),
    path("migrate/", migrate_marketing_page, name="migrate_marketing_page"),
    path(
        "migrate/<str:source_slug>/",
        migrate_marketing_page,
        name="migrate_marketing_page_source",
    ),
    path(
        "app-marketplace/",
        marketing_page,
        {"page_slug": "app-marketplace"},
        name="marketing_app_marketplace",
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
    path(
        "solutions/<str:topic_slug>/", topical_marketing_landing, name="marketing_topic"
    ),
    path(
        "cm/", regional_marketing_landing, {"country_code": "CM"}, name="marketing_cm"
    ),
    path(
        "ca/", regional_marketing_landing, {"country_code": "CA"}, name="marketing_ca"
    ),
    path(
        "setup-studio/", onboarding_wizard, name="setup_studio"
    ),  # Plan D1: canonical 8-step entry (currently delegates to onboarding_wizard)
    path("onboard/", onboarding_wizard, name="onboard_wizard"),
    path("signup/", signup_school, name="signup_school"),
    path("verify-signup/", verify_signup, name="verify_signup"),
    path("api/trial/", api_trial_school, name="api_trial_school"),
    path("lti/launch/<str:tool_id>/", lti_launch, name="lti_launch"),
    path(
        "lti/launch/<str:tool_id>/callback/",
        lti_launch_callback,
        name="lti_launch_callback",
    ),
    path(
        "lti/service/<str:tool_id>/lineitems",
        lti_ags_lineitems,
        name="lti_ags_lineitems",
    ),
    path(
        "lti/service/<str:tool_id>/lineitems/<str:lineitem_id>",
        lti_ags_lineitem_detail,
        name="lti_ags_lineitem_detail",
    ),
    path(
        "lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/scores",
        lti_ags_scores,
        name="lti_ags_scores",
    ),
    path(
        "lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/results",
        lti_ags_results,
        name="lti_ags_results",
    ),
    path(
        "lti/service/<str:tool_id>/memberships",
        lti_nrps_memberships,
        name="lti_nrps_memberships",
    ),
    path(
        "lti/service/<str:tool_id>/deep-linking",
        lti_deep_linking,
        name="lti_deep_linking",
    ),
    path("lti/jwks.json", jwks_json, name="lti_jwks"),
    path("account-frozen/", frozen_account, name="account_frozen"),
    # Resolve name for templates that link to operator help (manager host uses config.manager_urls; root needs name for tests/shared templates)
    path("help/", lambda request: redirect("public_support_hub"), name="manager_help"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
