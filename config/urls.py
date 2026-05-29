from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path, reverse
from django.views.i18n import set_language
from django.views.decorators.cache import cache_page
from django.views.generic.base import RedirectView
from drf_spectacular.views import SpectacularAPIView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.template.response import TemplateResponse
from django.http import HttpResponseForbidden

from apps.platform_runtime.helpers import get_effective_flags
from apps.platform_runtime.views_click_tracking import (
    click_measurement_dashboard,
    record_click_event,
)
from apps.platform_runtime.views_administration import internal_admin_alias_redirect
from apps.platform_runtime.views_rum import rum_ingest

from apps.observability import views as obs_views
from apps.observability import views_friction as obs_friction_views
from apps.portal.views_ai_copilot import (
    ai_copilot_query,
    ai_health,
    ai_permissions,
    ai_copilot_limits,
    ai_copilot_config,
    ai_copilot_audit_feed,
)
from apps.portal.views_configure import portal_configure_hub
from apps.portal.views_lexicon import lexicon_settings as portal_lexicon_settings_view
from apps.portal.views_at_risk_labeling import (
    at_risk_labeling_queue as portal_at_risk_labeling_view,
)
from apps.accounts.views_theme import set_theme_preference
from config.admin import platform_admin_site
from apps.schools.competitive_marketing_views import (
    marketing_implementation_assurance,
    marketing_pricing_packages_clarity,
    marketing_procurement_checklist,
    marketing_security_packet_request,
    marketing_story_page,
    marketing_trust_dedicated,
)
from apps.schools.marketing_region import MARKETING_LEGACY_REGIONAL_SHORTCUTS
from apps.schools.marketing_views import (
    marketing_landing,
    regional_marketing_landing,
    marketing_page,
    topical_marketing_landing,
    blog_post_detail,
    buyer_toolkit_download,
    developer_marketing_page,
    developer_portal,
    developer_sdk,
    developer_sandbox,
    marketing_funnel_dashboard,
    marketing_robots_txt,
    marketing_sitemap_xml,
    developer_public_api_docs,
    developer_hub,
    developer_console,
    migrate_marketing_page,
    migration_simulator_page,
    institution_marketing_page,
    role_marketing_page,
    marketing_verb_hub,
    submit_contact_request,
    submit_demo_request,
    submit_security_packet_request,
    marketing_intent_homepage,
    marketing_personality_page,
)
from apps.schools.signup_views import (
    signup_school,
    signup_slug_check,
    verify_signup,
    api_trial_school,
    onboarding_wizard,
    onboard_migration_handoff,
    onboard_migration_start,
)
from apps.schools.marketing_kb_views import (
    marketing_kb_article_view,
    marketing_kb_category_view,
    marketing_kb_search_view,
    marketing_kb_typeahead_api,
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


def service_worker_asset_manifest(request):
    """Return the SW pre-cache asset manifest as JSON with `static()`-resolved
    URLs. Lets the service worker pre-cache against the *actual* STATIC_URL
    (CDN, hashed-filename manifest, etc.) rather than hardcoded `/static/...`.

    Schema: `{ "version": str, "assets": [str, ...] }`. The version is taken
    from the SW CACHE_VERSION via env so SW + manifest stay in lockstep.

    See `docs/CONFIGURABILITY.md` (Layer B) + `reference_configurability_contract.md`.
    """
    from django.http import JsonResponse
    from django.templatetags.static import static as _static
    import os as _os

    paths = [
        "css/design-tokens.css",
        "css/dashboard-responsive.css",
        "css/reduce-motion-low-power.css",
        "js/command-palette.js",
        "js/dashboard-layout.js",
        "js/vendor/dexie.min.js",
        "js/offline-db.js",
        "js/form-draft-save.js",
        "js/sync-manager.js",
        "js/low-power.js",
        "js/offline-status-bar.js",
        "js/auto-pilot.js",
        "js/rmc-lexicon.js",
        "js/rmc-friction.js",
        "images/logo.png",
        "manifest.json",
    ]
    assets = ["/offline/"]
    for p in paths:
        try:
            assets.append(_static(p))
        except Exception:
            # collectstatic may not have run; fall through to raw /static/ path
            assets.append(f"/static/{p}")
    return JsonResponse(
        {
            "version": _os.getenv(
                "SW_MANIFEST_VERSION",
                "sms-v2.24.0-five-wave-closeout-2026-05-15",
            ),
            "assets": assets,
        }
    )


def manager_offline_sync_root_fallback(request):
    """
    Root-urlconf safety net for manager /offline/sync/.

    Host switching normally serves this from config.manager_urls. If a proxy,
    custom-domain cutover, or local smoke hits the root URLConf instead, avoid a
    raw 404 while preserving control-plane-only access.
    """
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    from apps.schools.control_plane import user_has_control_plane_access

    if not user_has_control_plane_access(request.user):
        return HttpResponseForbidden("Control-plane access required.")
    return render(
        request,
        "platform_runtime/manager_offline_sync_center.html",
        status=200,
    )


from config.error_handlers import (  # noqa: E402
    page_not_found,
    permission_denied,
    server_error,
    service_unavailable,
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
    SpectacularAPIView.as_view(permission_classes=[])
)


@login_required
@user_passes_test(_is_schema_allowed)
def schema_view(request):
    """API schema (JSON) – same access as schema UI."""
    return _schema_view_raw(request)


handler403 = permission_denied
handler404 = page_not_found
handler500 = server_error
handler503 = service_unavailable

from apps.security.csp_report_view import csp_violation_report  # noqa: E402
from apps.siteconfig.views_manifest import (  # noqa: E402
    platform_manifest as _platform_manifest,
    portal_manifest as _portal_manifest,
)
from apps.siteconfig.views_manifest_icon import (  # noqa: E402
    icon_any as _manifest_icon_any,
    icon_maskable as _manifest_icon_maskable,
)
from apps.siteconfig.views_tour import tour_steps_public_api  # noqa: E402
from apps.siteconfig.command_bar_registry import CommandBarActionsView  # noqa: E402
from apps.schools.marketing_views_v2 import marketing_landing_v2  # noqa: E402

# v3.39.0 Agent 4 — Prometheus HTTP scrape exporter is wired only when
# the prometheus-client backend is active; every other backend keeps
# /metrics/ unrouted so a misconfigured deployment never accidentally
# exposes an empty registry. See apps/observability/metrics.py.
_OBSERVABILITY_PROM_BACKEND = (
    getattr(settings, "OBSERVABILITY_METRICS_BACKEND", "noop") == "prometheus-client"
)

urlpatterns = [
    path("", home, name="home"),
    path("", home, name="marketing_home"),
    path("v2/", marketing_landing_v2, name="marketing_landing_v2"),
    path("storefront/", marketing_intent_homepage, name="marketing_intent_homepage"),
    path(
        "experience/<slug:personality_slug>/",
        marketing_personality_page,
        name="marketing_personality_page",
    ),
    path("offline/", offline_page, name="offline"),
    # Wave P-C (v3.95.1): Embedded checkout endpoint for parent fee payments.
    path(
        "billing/embedded-checkout/",
        __import__("django.urls", fromlist=["include"]).include(
            ("apps.billing.urls_embedded_checkout", "billing_embedded_checkout"),
            namespace="billing_embedded_checkout",
        ),
    ),
    path("sw-asset-manifest.json", service_worker_asset_manifest, name="sw_asset_manifest"),
    # v2.58 (2026-05-15) — per-tenant PWA manifest endpoints. Replaces the
    # static manifest.json / manifest-portal.json files so name / theme_color /
    # icons follow the active tenant's SiteSettings. See
    # apps/siteconfig/views_manifest.py for the render logic.
    path("manifest.json", _platform_manifest, name="pwa_manifest_platform"),
    path("manifest-portal.json", _portal_manifest, name="pwa_manifest_portal"),
    # v2.60 (2026-05-15) — sized PWA icon endpoints. Closes the Tier 1 gap
    # where the v2.59 manifest pointed at raw tenant logos that rarely
    # matched the spec-required 192/512 sizes, blocking the install
    # affordance. See apps/siteconfig/views_manifest_icon.py for the
    # Pillow resize + monogram fallback path.
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
    path(
        "offline/sync/",
        manager_offline_sync_root_fallback,
        name="manager_offline_sync_center",
    ),
    # Public tour-steps endpoint (registered here so marketing/trust templates
    # `{% url 'tour_steps_public_api' %}` resolve under the default urlconf in
    # tests that don't go through UrlConfSwitcherMiddleware).
    # rbac-allow: anonymous onboarding tour steps for marketing/login shells
    path("api/tour-steps/public/", tour_steps_public_api, name="tour_steps_public_api"),
    path("-/version/", obs_views.public_version, name="public_version"),
    # CSP violation report sink (browsers POST here per Content-Security-Policy-Report-Only).
    path("security/csp-report/", csp_violation_report, name="csp_violation_report"),
    # SOT batch 1204: redundant version endpoints so Render parity certifiers can
    # verify the deployed SHA even if a CDN or static layer captures the
    # leading-dash path. All three return identical JSON.
    path("api/system/version/", obs_views.public_version, name="api_system_version"),
    path("version.json", obs_views.public_version, name="public_version_json"),
    # Language switcher (Django i18n; POST language then redirect)
    path("i18n/setlang/", set_language, name="set_language"),
    path(
        "i18n/setlang/persist/",
        __import__("apps.accounts.views_i18n", fromlist=["set_language_persist"]).set_language_persist,
        name="set_language_persist",
    ),
    path("internal-admin/", internal_admin_alias_redirect, name="internal_admin"),
    path("internal-admin/<path:remaining>", internal_admin_alias_redirect),
    path(
        "admin/siteconfig/customizer/",
        __import__(
            "apps.siteconfig.legacy_redirects",
            fromlist=["legacy_customizer_redirect"],
        ).legacy_customizer_redirect,
    ),
    # Admin interfaces - /admin/ only for superuser/staff
    path("admin/", platform_admin_site.urls),
    # API schema (RBAC-protected; same as schema UI) — legacy DRF schema view.
    path("api/schema/", schema_view, name="api-schema"),
    path("api/schema/ui/", api_schema_ui, name="api-schema-ui"),
    # drf-spectacular OpenAPI 3.0 surfaces — public developer documentation.
    # /api/openapi.json + /api/openapi.yaml: raw OpenAPI spec (machine-readable).
    # /api/docs/: Swagger UI for interactive exploration.
    # /api/redoc/: Redoc for a cleaner reference look.
    # These are intentionally unauthenticated — they describe the API surface, not the data.
    # Per-endpoint auth requirements are documented in the spec.
    path(
        "api/openapi.json",
        __import__(
            "drf_spectacular.views", fromlist=["SpectacularAPIView"]
        ).SpectacularAPIView.as_view(permission_classes=[]),
        name="openapi-schema",
    ),
    path(
        "api/openapi.yaml",
        __import__(
            "drf_spectacular.views", fromlist=["SpectacularAPIView"]
        ).SpectacularAPIView.as_view(permission_classes=[], renderer_classes=[
            __import__(
                "drf_spectacular.renderers", fromlist=["OpenApiYamlRenderer"]
            ).OpenApiYamlRenderer
        ]),
        name="openapi-schema-yaml",
    ),
    path(
        "api/docs/",
        __import__(
            "drf_spectacular.views", fromlist=["SpectacularSwaggerView"]
        ).SpectacularSwaggerView.as_view(
            url_name="openapi-schema", permission_classes=[]
        ),
        name="openapi-swagger-ui",
    ),
    path(
        "api/redoc/",
        __import__(
            "drf_spectacular.views", fromlist=["SpectacularRedocView"]
        ).SpectacularRedocView.as_view(
            url_name="openapi-schema", permission_classes=[]
        ),
        name="openapi-redoc",
    ),
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
    # v4.00.2 audit: mirror ``activation_first_action`` from config.tenant_urls
    # so ConversionLockMiddleware / ActivationGateMiddleware can resolve the
    # name regardless of which URLconf is active on the responding host. Path
    # + url-name come from the activation_views SOT module.
    path(
        __import__(
            "apps.schools.activation_views",
            fromlist=["ACTIVATION_FIRST_ACTION_PATH"],
        ).ACTIVATION_FIRST_ACTION_PATH.lstrip("/"),
        __import__(
            "apps.schools.activation_views", fromlist=["activation_first_action"]
        ).activation_first_action,
        name=__import__(
            "apps.schools.activation_views",
            fromlist=["ACTIVATION_FIRST_ACTION_URL_NAME"],
        ).ACTIVATION_FIRST_ACTION_URL_NAME,
    ),
    # Health and metrics
    path("healthz/", obs_views.healthz, name="healthz"),
    # Offline foundational: fresh CSRF token endpoint for SW replay (cookie may
    # have rotated while POSTs were queued in IndexedDB). Auth-required so we
    # never leak rotation timing to anonymous probes, but NOT gated by
    # observability_auth_required — the SW serves parents/students.
    path("api/csrf-token/", obs_views.csrf_token_refresh, name="api_csrf_token"),
    # Public health endpoint for load balancers
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_status, name="status"),
    path("metrics/", obs_views.metrics, name="metrics"),
    path(
        "api/observability/copilot-metrics/",
        obs_views.copilot_metrics_json,
        name="copilot_metrics_json",
    ),
    # Pass 11.B: server-side bridge for browser / SW error capture (CDN-free).
    path(
        "api/observability/client-event/",
        obs_views.client_event_capture,
        name="client_event_capture",
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
    # Wave B — G5: user-friction telemetry ingest.
    path(
        "api/observability/friction/",
        obs_friction_views.ingest_friction_event,
        name="api_friction_ingest",
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
    # Universal Command Bar (v3.53.0, 2026-05-21) — server-side action
    # registry consumed by the cmd+k overlay loaded into all 4 dashboard shells.
    # # rbac-allow: command-bar-server-filters-actions-per-user-and-tenant
    path(
        "api/command-bar/actions/",
        CommandBarActionsView.as_view(),
        name="command_bar_actions",
    ),
    path("api/ai-copilot/validate/", ai_copilot_query, name="ai_copilot_query"),
    path("api/ai-copilot/permissions/", ai_permissions, name="ai_permissions"),
    path("api/ai-copilot/limits/", ai_copilot_limits, name="ai_copilot_limits"),
    path("api/ai-copilot/config/", ai_copilot_config, name="ai_copilot_config"),
    path("api/ai-copilot/audit/", ai_copilot_audit_feed, name="ai_copilot_audit"),
    # Phase E (2026-05-12): cached reachability probe used by the floating copilot UI
    # so degraded mode is visible to users instead of silently failing.
    path("api/ai/health/", ai_health, name="ai_health"),
    # Theme v2 (2026-05-12): server-side persistence of Light/Dark/System preference.
    path("api/preferences/theme/", set_theme_preference, name="set_theme_preference"),
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
    path("api/v1/oauth/", include(("apps.apicenter.oauth_urls", "oauth"), namespace="oauth")),
    path("api/v2/", include(("apps.api.urls_v2", "api_v2"), namespace="api_v2")),
    # v4.00.36 — SAML 2.0 SP endpoints (wedge 45). Routed at the platform
    # root so IdP redirect URIs stay stable (operators register the ACS URL).
    path("sso/saml/metadata/", __import__("apps.api.saml", fromlist=["metadata"]).metadata, name="sso_saml_metadata"),
    path("sso/saml/acs/", __import__("apps.api.saml", fromlist=["acs"]).acs, name="sso_saml_acs"),
    path("sso/saml/sls/", __import__("apps.api.saml", fromlist=["sls"]).sls, name="sso_saml_sls"),
    # Apps
    path(
        "siteconfig/",
        include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig"),
    ),
    path(
        "studio/", include(("apps.studio_os.urls", "studio_os"), namespace="studio_os")
    ),
    # Unified Wizard Framework (operator + tenant surfaces share one engine).
    # Routes: /super/wizards/..., /school/studio/wizards/..., /api/wizards/...
    path("", include(("apps.setup_studio.urls", "setup_studio"), namespace="setup_studio")),
    path(
        "configuration/",
        include(
            ("apps.platform_runtime.configuration_urls", "configuration"),
            namespace="configuration",
        ),
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
    # Phase F (2026-05-12): tenant operator URL grammar — same split that exists for
    # the platform (/super = everyday management, /admin = configuration). For tenants:
    #   /portal/console/   → everyday running of the school (operator workbench)
    #   /portal/configure/ → tenant configuration (settings, branding, blueprint pack)
    # These are canonical aliases so the URL itself signals *which mode* the user is in,
    # the way Stripe Dashboard vs Settings or Shopify Admin vs Settings work.
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
    # Wave F (2026-05-15): tenant lexicon settings UI with live preview.
    path(
        "portal/configure/lexicon/",
        portal_lexicon_settings_view,
        name="portal_lexicon_settings",
    ),
    # Wave O4 (2026-05-15): at-risk outcome labeling queue for retrospective
    # ML training data (admin/principal/proprietor role gate).
    path(
        "portal/at-risk/labeling/",
        portal_at_risk_labeling_view,
        name="portal_at_risk_labeling",
    ),
    path("kb/", include(("apps.portal.urls_kb", "kb"), namespace="kb")),
    # Move 1 (developer platform): public marketplace catalog detail, search API, publisher signup.
    path(
        "marketplace/",
        include(("apps.marketplace.urls_developer_platform", "marketplace_dev"), namespace="marketplace_dev"),
    ),
    # Move 2 (workflow engine): orchestration JSON API + workbench.
    path(
        "orchestration/",
        include(("apps.orchestration.urls", "orchestration"), namespace="orchestration"),
    ),
    # Wave v2.69 (2026-05-16): integrations marketplace hub + OAuth dance for
    # per-school / per-campus external connectors (Zoom, Teams, Meet, Outlook,
    # Gmail, Calendar, Slack, transactional mail providers).
    path(
        "integrations/",
        include(
            ("apps.integrations_marketplace.urls", "integrations_marketplace"),
            namespace="integrations_marketplace",
        ),
    ),
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
    path("", include(("apps.feedback.urls", "feedback"), namespace="feedback")),
    path(
        "super/feedback/",
        include(("apps.feedback.operator_urls", "feedback_operator"), namespace="feedback_operator"),
    ),
    path(
        "organization/network/",
        parent_tenant_dashboard,
        name="organization_network_dashboard",
    ),
    # Super Admin (multi-tenant provisioning)
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    # Migration Cloud — operator console (Phase U6 LIVE as of v3.38+: audit dashboard,
    # health view, webhook subscriptions admin, MAA v2.0 promotion dashboard).
    # v4.00.12 closeout: comment updated to reflect shipped state.
    path(
        "super/migration/",
        include(("apps.migration_cloud.urls", "migration_cloud_super"), namespace="migration_cloud_super"),
        {"shell": "super"},
    ),
    # Migration Cloud — tenant mirror (plan-gated upstream; same URL grammar).
    path(
        "portal/configure/migration/",
        include(("apps.migration_cloud.urls", "migration_cloud_portal"), namespace="migration_cloud_portal"),
        {"shell": "portal"},
    ),
    # v3.40.0 Agent 7 — customer-facing intake + status flow. Tenant-scoped
    # (login-required, tenant-isolated). Distinct from the operator (super)
    # and tenant-mirror (portal/configure) namespaces above: this is the
    # surface the school's own staff use to request a migration, sign the
    # MAA, and monitor progress.
    path(
        "migration/",
        include(
            ("apps.migration_cloud.urls_customer", "migration_intake_customer"),
            namespace="migration_intake_customer",
        ),
    ),
    # v3.40.0 Agent 11 — guardian consent collection flow.
    # Anonymous (token-in-URL) namespace for guardian-facing routes;
    # tenant-scoped (LoginRequiredMixin) admin namespace for school
    # staff. Two separate mounts so the anonymous reverse-resolve
    # cannot accidentally compose intake-id semantics.
    path(
        "migration/consent/",
        include(
            (
                "apps.migration_cloud.urls_guardian_consent",
                "migration_guardian_consent",
            ),
            namespace="migration_guardian_consent",
        ),
    ),
    path(
        "migration/",
        include(
            (
                "apps.migration_cloud.urls_guardian_consent_admin",
                "migration_guardian_consent_admin",
            ),
            namespace="migration_guardian_consent_admin",
        ),
    ),
    # §3.3 Metadata search (staff-only)
    path(
        "api/internal/metadata/",
        include(("apps.metadata.urls", "metadata"), namespace="metadata"),
    ),
    path("api/internal/rum/", rum_ingest, name="rum_ingest"),
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
        "platform-runtime/",
        include(
            ("apps.platform_runtime.urls", "platform_runtime"),
            namespace="platform_runtime",
        ),
    ),
    # Section 8: Caddy on-demand TLS ask (no auth; restrict by IP in production)
    path("api/caddy-check/", verify_caddy_domain),
    path("api/v1/auth/check-domain/", verify_caddy_domain),
    path("discover/", global_login_discovery, name="global_login_discovery"),
    path("find/", find_school, name="find_school"),
    path("verify/", public_verify_hub, name="public_verify_hub"),
    path("support/", public_support_hub, name="public_support_hub"),
    path("robots.txt", marketing_robots_txt, name="marketing_robots_txt"),
    path("sitemap.xml", marketing_sitemap_xml, name="marketing_sitemap_xml"),
    path(
        "demo/",
        marketing_page,
        {"page_slug": "demo"},
        name="marketing_demo",
    ),
    path(
        "resources/product-tour/",
        marketing_page,
        {"page_slug": "resources-product-tour"},
        name="marketing_resources_product_tour",
    ),
    path(
        "resources/blog/",
        marketing_page,
        {"page_slug": "resources-blog"},
        name="marketing_resources_blog",
    ),
    path(
        "company/",
        marketing_page,
        {"page_slug": "company"},
        name="marketing_company",
    ),
    path(
        "resources/case-studies/",
        marketing_page,
        {"page_slug": "resources-case-studies"},
        name="marketing_resources_case_studies",
    ),
    path(
        "resources/guides/",
        marketing_page,
        {"page_slug": "resources-guides"},
        name="marketing_resources_guides",
    ),
    path(
        "resources/help-center/",
        marketing_page,
        {"page_slug": "resources-help-center"},
        name="marketing_resources_help_center",
    ),
    path(
        "resources/help-center/search/",
        marketing_kb_search_view,
        name="marketing_kb_search",
    ),
    path(
        "resources/help-center/category/<slug:category_slug>/",
        marketing_kb_category_view,
        name="marketing_kb_category",
    ),
    path(
        "resources/help-center/article/<slug:article_slug>/",
        marketing_kb_article_view,
        name="marketing_kb_article",
    ),
    path(
        "api/v1/marketing/kb/typeahead/",
        marketing_kb_typeahead_api,
        name="marketing_kb_typeahead",
    ),
    path(
        "solutions/k12-schools/",
        institution_marketing_page,
        {"institution_slug": "k12-schools"},
        name="institution_k12_schools",
    ),
    path(
        "solutions/k12-schools/",
        institution_marketing_page,
        {"institution_slug": "k12-schools"},
        name="marketing_solutions_k12_schools",
    ),
    path("marketing/", marketing_landing, name="marketing_landing"),
    path("grow/", marketing_verb_hub, {"verb": "grow"}, name="marketing_grow_hub"),
    path(
        "grow/marketplace/",
        marketing_page,
        {"page_slug": "platform-marketplace"},
        name="marketing_grow_marketplace",
    ),
    path(
        "grow/migration/",
        marketing_page,
        {"page_slug": "platform-migration-cloud"},
        name="marketing_grow_migration",
    ),
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
        "platform/student-information-system/",
        marketing_page,
        {"page_slug": "platform-student-information-system"},
        name="marketing_platform_sis",
    ),
    path(
        "platform/admissions/",
        marketing_page,
        {"page_slug": "platform-admissions"},
        name="marketing_platform_admissions",
    ),
    path(
        "platform/attendance/",
        marketing_page,
        {"page_slug": "platform-attendance"},
        name="marketing_platform_attendance",
    ),
    path(
        "platform/fees-payments/",
        marketing_page,
        {"page_slug": "platform-fees-payments"},
        name="marketing_platform_fees_payments",
    ),
    path(
        "platform/grading-report-cards/",
        marketing_page,
        {"page_slug": "platform-grading-report-cards"},
        name="marketing_platform_grading_report_cards",
    ),
    path(
        "platform/parent-portal/",
        marketing_page,
        {"page_slug": "platform-parent-portal"},
        name="marketing_platform_parent_portal",
    ),
    path(
        "platform/teacher-portal/",
        marketing_page,
        {"page_slug": "platform-teacher-portal"},
        name="marketing_platform_teacher_portal",
    ),
    path(
        "platform/student-portal/",
        marketing_page,
        {"page_slug": "platform-student-portal"},
        name="marketing_platform_student_portal",
    ),
    path(
        "platform/communications/",
        marketing_page,
        {"page_slug": "platform-communications"},
        name="marketing_platform_communications",
    ),
    path(
        "platform/workflows/",
        marketing_page,
        {"page_slug": "platform-workflows"},
        name="marketing_platform_workflows",
    ),
    path(
        "platform/offline-first/",
        marketing_page,
        {"page_slug": "platform-offline-first"},
        name="marketing_platform_offline_first",
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
        RedirectView.as_view(url="/solutions/k12-schools/", permanent=True),
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
        "solutions/private-schools/",
        institution_marketing_page,
        {"institution_slug": "private-schools"},
        name="marketing_solutions_private_schools",
    ),
    path(
        "solutions/government-education/",
        institution_marketing_page,
        {"institution_slug": "government-education"},
        name="institution_government_education",
    ),
    path(
        "solutions/international-schools/",
        institution_marketing_page,
        {"institution_slug": "international-schools"},
        name="institution_international_schools",
    ),
    path(
        "solutions/international-schools/",
        institution_marketing_page,
        {"institution_slug": "international-schools"},
        name="marketing_solutions_international_schools",
    ),
    path(
        "solutions/faith-based-schools/",
        institution_marketing_page,
        {"institution_slug": "faith-based-schools"},
        name="institution_faith_based_schools",
    ),
    path(
        "solutions/faith-based-schools/",
        institution_marketing_page,
        {"institution_slug": "faith-based-schools"},
        name="marketing_solutions_faith_based_schools",
    ),
    path(
        "solutions/multi-campus/",
        institution_marketing_page,
        {"institution_slug": "multi-campus"},
        name="institution_multi_campus",
    ),
    path(
        "solutions/multi-campus/",
        institution_marketing_page,
        {"institution_slug": "multi-campus"},
        name="marketing_solutions_multi_campus",
    ),
    path(
        "solutions/growing-school-networks/",
        institution_marketing_page,
        {"institution_slug": "growing-school-networks"},
        name="institution_growing_school_networks",
    ),
    path(
        "solutions/growing-school-networks/",
        institution_marketing_page,
        {"institution_slug": "growing-school-networks"},
        name="marketing_solutions_growing_school_networks",
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
        "roles/principals/",
        role_marketing_page,
        {"role_slug": "principals"},
        name="role_principals",
    ),
    path(
        "roles/district-leaders/",
        role_marketing_page,
        {"role_slug": "district-leaders"},
        name="role_district_leaders",
    ),
    path(
        "roles/finance/",
        role_marketing_page,
        {"role_slug": "finance"},
        name="role_finance",
    ),
    path(
        "pricing/", marketing_page, {"page_slug": "pricing"}, name="marketing_pricing"
    ),
    path(
        "pricing-packages/",
        marketing_pricing_packages_clarity,
        name="marketing_pricing_packages_clarity",
    ),
    path("trust/", marketing_trust_dedicated, name="marketing_trust_dedicated"),
    path(
        "implementation/",
        marketing_story_page,
        {"story_slug": "implementation"},
        name="marketing_story_implementation",
    ),
    path(
        "offline-first/",
        marketing_story_page,
        {"story_slug": "offline-first"},
        name="marketing_story_offline_first",
    ),
    path(
        "payments-readiness/",
        marketing_story_page,
        {"story_slug": "payments-readiness"},
        name="marketing_story_payments_readiness",
    ),
    path(
        "for-private-schools/",
        marketing_story_page,
        {"story_slug": "for-private-schools"},
        name="marketing_story_private_schools",
    ),
    path(
        "for-school-networks/",
        marketing_story_page,
        {"story_slug": "for-school-networks"},
        name="marketing_story_school_networks",
    ),
    path(
        "pilot-program/",
        marketing_story_page,
        {"story_slug": "pilot-program"},
        name="marketing_story_pilot_program",
    ),
    path(
        "procurement-checklist/",
        marketing_procurement_checklist,
        name="marketing_procurement_checklist",
    ),
    path(
        "procurement-docs/",
        RedirectView.as_view(
            pattern_name="marketing_procurement_checklist", permanent=False
        ),
        name="marketing_procurement_docs",
    ),
    path(
        "implementation-timelines/",
        RedirectView.as_view(
            pattern_name="marketing_implementation_assurance", permanent=False
        ),
        name="marketing_implementation_timelines",
    ),
    path(
        "portal-login/",
        RedirectView.as_view(pattern_name="global_login_discovery", permanent=False),
        name="marketing_portal_login",
    ),
    path(
        "find-campus-portal/",
        RedirectView.as_view(pattern_name="find_school", permanent=False),
        name="marketing_find_campus_portal",
    ),
    path(
        "careers/",
        marketing_page,
        {"page_slug": "careers"},
        name="marketing_careers",
    ),
    path(
        "brand-assets/",
        marketing_page,
        {"page_slug": "brand-assets"},
        name="marketing_brand_assets",
    ),
    path(
        "hardware-store/",
        marketing_page,
        {"page_slug": "hardware-store"},
        name="marketing_hardware_store",
    ),
    path(
        "training-academies/",
        marketing_page,
        {"page_slug": "training-academies"},
        name="marketing_training_academies",
    ),
    path(
        "teacher-communities/",
        marketing_page,
        {"page_slug": "teacher-communities"},
        name="marketing_teacher_communities",
    ),
    path(
        "lesson-planning/",
        marketing_page,
        {"page_slug": "lesson-planning"},
        name="marketing_lesson_planning",
    ),
    path(
        "infrastructure-map/",
        marketing_page,
        {"page_slug": "infrastructure-map"},
        name="marketing_infrastructure_map",
    ),
    path(
        "security-matrix/",
        marketing_page,
        {"page_slug": "security-matrix"},
        name="marketing_security_matrix",
    ),
    path(
        "solutions/higher-ed/",
        marketing_page,
        {"page_slug": "solutions-higher-ed"},
        name="marketing_solutions_higher_ed",
    ),
    path(
        "solutions/k12-districts/",
        marketing_page,
        {"page_slug": "solutions-k12-districts"},
        name="marketing_solutions_k12_districts",
    ),
    path(
        "legal-compliance/ferpa/",
        marketing_page,
        {"page_slug": "legal-ferpa"},
        name="marketing_legal_ferpa",
    ),
    path(
        "legal-compliance/coppa/",
        marketing_page,
        {"page_slug": "legal-coppa"},
        name="marketing_legal_coppa",
    ),
    path(
        "legal-compliance/gdpr/",
        marketing_page,
        {"page_slug": "legal-gdpr"},
        name="marketing_legal_gdpr",
    ),
    path(
        "legal-compliance/wcag/",
        marketing_page,
        {"page_slug": "legal-wcag"},
        name="marketing_legal_wcag",
    ),
    path(
        "legal-compliance/terms/",
        marketing_page,
        {"page_slug": "legal-terms"},
        name="marketing_legal_terms",
    ),
    path(
        "legal-compliance/cookie-policy/",
        marketing_page,
        {"page_slug": "legal-cookie"},
        name="marketing_legal_cookie",
    ),
    path(
        "implementation-assurance/",
        marketing_implementation_assurance,
        name="marketing_implementation_assurance",
    ),
    path(
        "security-packet/",
        marketing_security_packet_request,
        name="marketing_security_packet_request",
    ),
    path(
        "compare/", marketing_page, {"page_slug": "compare"}, name="marketing_compare"
    ),
    path(
        "case-studies/",
        RedirectView.as_view(url="/resources/case-studies/", permanent=True),
        name="marketing_case_studies",
    ),
    path(
        "customers/",
        RedirectView.as_view(
            pattern_name="marketing_resources_case_studies", permanent=False
        ),
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
        RedirectView.as_view(pattern_name="marketing_demo", permanent=False),
        name="marketing_book_demo",
    ),
    path("book-demo/submit/", submit_demo_request, name="marketing_book_demo_submit"),
    path(
        "interactive-preview/",
        marketing_page,
        {"page_slug": "interactive-preview"},
        name="marketing_interactive_preview",
    ),
    path(
        "product-tour/",
        RedirectView.as_view(
            pattern_name="marketing_resources_product_tour", permanent=False
        ),
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
    path(
        "blog/",
        RedirectView.as_view(url="/resources/blog/", permanent=True),
        name="marketing_blog",
    ),
    path("blog/<slug:slug>/", blog_post_detail, name="marketing_blog_detail"),
    path(
        "contact/submit/",
        submit_contact_request,
        name="marketing_contact_submit",
    ),
    path(
        "security-packet/submit/",
        submit_security_packet_request,
        name="marketing_security_packet_submit",
    ),
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
    path(
        "guides/",
        RedirectView.as_view(url="/resources/guides/", permanent=True),
        name="marketing_guides",
    ),
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
        "trust-center/coppa/",
        marketing_page,
        {"page_slug": "trust-center-coppa"},
        name="marketing_trust_coppa",
    ),
    path(
        "trust-center/accessibility/",
        marketing_page,
        {"page_slug": "trust-center-accessibility"},
        name="marketing_trust_accessibility",
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
        "developers/api/",
        developer_marketing_page,
        {"section_slug": "api"},
        name="developer_api",
    ),
    path(
        "developers/webhooks/",
        developer_marketing_page,
        {"section_slug": "webhooks"},
        name="developer_webhooks",
    ),
    path(
        "developers/integrations/",
        developer_marketing_page,
        {"section_slug": "integrations"},
        name="developer_integrations",
    ),
    path(
        "developers/sdk/",
        developer_marketing_page,
        {"section_slug": "sdk"},
        name="developer_sdk_page",
    ),
    path(
        "developers/app-building/",
        developer_marketing_page,
        {"section_slug": "app-building"},
        name="developer_app_building",
    ),
    path(
        "developers/api-docs/",
        developer_public_api_docs,
        name="developer_public_api_docs",
    ),
    path("developer/", developer_hub, name="developer_hub"),
    path("developer/console/", developer_console, name="developer_console"),
    path("developer-portal/", developer_portal, name="developer_portal"),
    path("developer-portal/sdk/", developer_sdk, name="developer_sdk"),
    path("developer-portal/sandbox/", developer_sandbox, name="developer_sandbox"),
    path("migrate/", migrate_marketing_page, name="migrate_marketing_page"),
    path("migrate/simulator/", migration_simulator_page, name="migration_simulator"),
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
    *[
        path(
            f"{prefix}/",
            regional_marketing_landing,
            {"country_code": country, "language_code": lang},
            name=url_name,
        )
        for prefix, country, lang, url_name in MARKETING_LEGACY_REGIONAL_SHORTCUTS
    ],
    path(
        "<str:language_code>/<str:country_code>/",
        regional_marketing_landing,
        name="marketing_region",
    ),
    path(
        "setup-studio/", onboarding_wizard, name="setup_studio"
    ),  # Public 3-step onboarding (delegates to onboarding_wizard); post-signup setup lives in siteconfig Setup Studio
    path("onboard/", onboarding_wizard, name="onboard_wizard"),
    path("onboard/migrate/", onboard_migration_handoff, name="onboard_migration_handoff"),
    path("onboard/migrate/start/", onboard_migration_start, name="onboard_migration_start"),
    path("signup/", signup_school, name="signup_school"),
    path("signup/slug-check/", signup_slug_check, name="signup_slug_check"),
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

# v3.39.0 Agent 4 — Prometheus scrape endpoint (lazy include).
if _OBSERVABILITY_PROM_BACKEND:
    from apps.observability.views_metrics import PrometheusMetricsView  # noqa: E402

    urlpatterns += [
        path("metrics/", PrometheusMetricsView.as_view(), name="prometheus_metrics"),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
