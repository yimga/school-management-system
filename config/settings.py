from pathlib import Path
import os
import re
import sys
from dotenv import load_dotenv

# Optional: Django Channels for WebSocket AI chat (ws/ai/chat/). If installed, enabled below.
try:
    import channels  # noqa: F401

    _channels_installed = True
except ImportError:
    _channels_installed = False

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()
# .env.local: do not override vars already set (e.g. DATABASE_URL on Render), so local file only fills in unset keys.
load_dotenv(BASE_DIR / ".env.local", override=False)
RUNNING_TESTS = "test" in sys.argv or any(
    "pytest" in (arg or "") for arg in sys.argv
) or bool(os.getenv("PYTEST_CURRENT_TEST"))

from django.core.exceptions import ImproperlyConfigured

from apps.schools.marketing_settings_helpers import derive_marketing_demo_tenant_url

SECRET_KEY = os.getenv("SECRET_KEY")
_is_render = os.getenv("RENDER", "").lower() == "true"
_debug_default = "0" if _is_render else "1"
DEBUG = os.getenv("DEBUG", _debug_default) == "1"

# GraphQL introspection: off in production unless explicitly enabled (GEOS-99 batch 1384).
_graphql_intro_raw = os.getenv("GRAPHQL_INTROSPECTION_ENABLED", "").strip().lower()
if _graphql_intro_raw in ("1", "true", "yes"):
    GRAPHQL_INTROSPECTION_ENABLED = True
elif _graphql_intro_raw in ("0", "false", "no"):
    GRAPHQL_INTROSPECTION_ENABLED = False
else:
    GRAPHQL_INTROSPECTION_ENABLED = DEBUG

# Incident routing: any 500 in production should email the security/ops team.
# Comma-separated env var: ADMINS_EMAILS="ops@example.com,security@example.com".
_admins_raw = (os.getenv("ADMINS_EMAILS") or "").strip()
ADMINS = [
    ("Operations", email.strip())
    for email in _admins_raw.split(",")
    if email.strip()
] if _admins_raw else []
MANAGERS = ADMINS
SERVER_EMAIL = os.getenv("SERVER_EMAIL", "no-reply@runmycampus.com")
# Deploy tier: used so staging keeps strict conversion + paid billing even when DEBUG=1 locally on Render.
_RMC_DEPLOY_ENV = (
    os.getenv("RMC_ENVIRONMENT") or os.getenv("DJANGO_ENV") or ""
).strip().lower()
_IS_PRODUCTION_OR_STAGING = _RMC_DEPLOY_ENV in (
    "production",
    "prod",
    "staging",
    "stage",
)
# Hosted deploy (Render/Heroku-style): enforce conversion + paid-install billing even when DEBUG=1.
_IS_CLOUD_DEPLOYED = _is_render or _IS_PRODUCTION_OR_STAGING
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-change-in-production"
    else:
        raise ImproperlyConfigured("SECRET_KEY must be set in production.")

ALLOWED_HOSTS_RAW = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,.local,.localhost")
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_RAW.split(",") if host.strip()]
# Render.com: allow *.onrender.com so login and all URLs work without setting ALLOWED_HOSTS in dashboard
if os.getenv("RENDER") == "true":
    if ".onrender.com" not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(".onrender.com")
# Multi-tenant: allow main host and subdomains.
# Production default canonical domain is runmycampus.com.
_multi_tenant_base = (
    os.getenv(
        "MULTI_TENANT_BASE_DOMAIN",
        "runmycampus.com",
    )
    .strip()
    .lower()
)
_legacy_bases_raw = (
    (os.getenv("MULTI_TENANT_LEGACY_BASE_DOMAINS") or "").strip().lower()
)
_legacy_bases = [d.strip() for d in _legacy_bases_raw.split(",") if d.strip()]
# Exposed for host_routing and tests (`@override_settings(MULTI_TENANT_BASE_DOMAIN=...)`).
MULTI_TENANT_BASE_DOMAIN = _multi_tenant_base
# Studio OS / manager deep links (Render: set in dashboard)
MANAGER_PLATFORM_BASE_URL = (
    os.getenv("MANAGER_PLATFORM_BASE_URL", "https://manager.runmycampus.com")
    .strip()
    .rstrip("/")
)
# OAuth redirect/callback base (Zoom, Google, Microsoft, Slack app consoles).
# Explicit env wins; in production default to the manager control plane so boot
# does not warn on every migrate/predeploy when the var is unset.
_oauth_callback_base = (os.getenv("OAUTH_CALLBACK_BASE_URL") or "").strip().rstrip("/")
if not _oauth_callback_base and not DEBUG:
    _oauth_callback_base = MANAGER_PLATFORM_BASE_URL or "https://manager.runmycampus.com"
OAUTH_CALLBACK_BASE_URL = _oauth_callback_base
# Public marketing site URL — env-driven so the platform brand domain is configurable
# per environment (staging vs prod) and never hardcoded in views/templates.
# Read in templates as `{{ public_site_url }}` (via context processor) or as
# `settings.PUBLIC_SITE_URL` in Python.
PUBLIC_SITE_URL = (
    os.getenv("PUBLIC_SITE_URL", "https://runmycampus.com").strip().rstrip("/")
)
STUDIO_APPROVAL_HUB_TENANT_BASE_URL = (
    os.getenv("STUDIO_APPROVAL_HUB_TENANT_BASE_URL", "").strip().rstrip("/")
)

if _multi_tenant_base:
    if _multi_tenant_base not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_multi_tenant_base)
    _dotted_base = f".{_multi_tenant_base}"
    if _dotted_base not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_dotted_base)
for _legacy_base in _legacy_bases:
    if _legacy_base not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_legacy_base)
    _dotted_legacy = f".{_legacy_base}"
    if _dotted_legacy not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_dotted_legacy)
# Default host for Django's test client and pytest-django.
if "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be configured for production.")

# Behind HTTPS proxy (e.g. Render, Heroku): trust X-Forwarded-Proto and X-Forwarded-Host
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
# CSRF: allow HTTPS origins (Django 4.0+). On Render, set CSRF_TRUSTED_ORIGINS or RENDER_EXTERNAL_HOSTNAME is used.
_csrf_origins = os.getenv("CSRF_TRUSTED_ORIGINS", "").strip()
_render_host = (os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip()
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [s.strip() for s in _csrf_origins.split(",") if s.strip()]
elif _render_host:
    CSRF_TRUSTED_ORIGINS = [f"https://{_render_host}"]
else:
    CSRF_TRUSTED_ORIGINS = []
# District roster push webhook (HMAC). Per-school override: school.settings["roster_webhook_secret"]
ONEROSTER_WEBHOOK_SECRET = (os.getenv("ONEROSTER_WEBHOOK_SECRET") or "").strip()
# RUM: optional ingest token (>= 16 chars). When set, portal/marketing load rum-beacon.js.
RUM_INGEST_KEY = (os.getenv("RUM_INGEST_KEY") or "").strip()
# Marketplace: default platform take on gross tenant app charges (see apps.marketplace.monetization).
MARKETPLACE_PLATFORM_FEE_PERCENT = (os.getenv("MARKETPLACE_PLATFORM_FEE_PERCENT") or "20").strip()
# When True, installing a paid catalog app (compute_install_charge > 0) requires a billing account with processor customer.
_default_marketplace_paid_billing = (
    ""
    if RUNNING_TESTS
    else ("1" if ((not DEBUG) or _IS_CLOUD_DEPLOYED) else "")
)
MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING = (
    os.getenv(
        "MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING",
        _default_marketplace_paid_billing,
    ).strip().lower()
    in ("1", "true", "yes")
)
# Multi-tenant: ensure main domain HTTPS origin is trusted when MULTI_TENANT_BASE_DOMAIN is set
if _multi_tenant_base:
    _origin = f"https://{_multi_tenant_base}"
    if _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = list(CSRF_TRUSTED_ORIGINS) + [_origin]
    _wildcard_origin = f"https://*.{_multi_tenant_base}"
    if _wildcard_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = list(CSRF_TRUSTED_ORIGINS) + [_wildcard_origin]
for _legacy_base in _legacy_bases:
    _legacy_origin = f"https://{_legacy_base}"
    if _legacy_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = list(CSRF_TRUSTED_ORIGINS) + [_legacy_origin]
    _legacy_wildcard = f"https://*.{_legacy_base}"
    if _legacy_wildcard not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = list(CSRF_TRUSTED_ORIGINS) + [_legacy_wildcard]

INSTALLED_APPS = [
    # Admin theme (must be first)
    "unfold",
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Django OTP (MFA)
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    # REST Framework
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    # OpenAPI / Swagger UI / Redoc auto-generation from DRF code.
    # Exposed at /api/schema/, /api/docs/ (Swagger UI), /api/redoc/.
    "drf_spectacular",
    # GraphQL
    "graphene_django",
    # Project apps
    "apps.accounts.apps.AccountsConfig",
    "apps.customers",
    "apps.tenancy.apps.TenancyConfig",
    "apps.policies.apps.PoliciesConfig",
    "apps.events.apps.EventsConfig",
    "apps.marketplace.apps.MarketplaceConfig",
    "apps.registries.apps.RegistriesConfig",
    "apps.billing",  # Entitlements: can(), limits(), usage() (blueprint A1)
    "apps.sales.apps.SalesConfig",  # Internal founder pipeline (public schema; manager host)
    "apps.student360",  # Student 360: timeline feed, export pack (blueprint B1)
    "apps.school_events.apps.SchoolEventsConfig",
    "apps.evals",
    "apps.portal",
    "apps.academics",
    "apps.people",
    "apps.reports",
    "apps.siteconfig.apps.SiteconfigConfig",
    "apps.schools",
    "apps.security.apps.SecurityConfig",
    "apps.schoolops.apps.SchoolOpsConfig",
    "apps.analytics",
    "apps.dashboard.apps.DashboardConfig",
    "apps.finance",
    "payment",
    "apps.payroll",
    "apps.compliance.apps.ComplianceConfig",
    "apps.communication",
    "apps.requests",
    "apps.feedback.apps.FeedbackConfig",
    "apps.observability.apps.ObservabilityConfig",  # Observability/monitoring
    "apps.customersuccess",  # Section 11: Benchmark intelligence, customer success, health
    "apps.api",
    "apps.sync_engine.apps.SyncEngineConfig",
    "apps.apicenter",
    "apps.automation",  # Automation and background tasks
    "apps.migration_cloud.apps.MigrationCloudConfig",  # Universal Migration Cloud (Phase U1+)
    "apps.metadata.apps.MetadataConfig",  # Custom fields without DDL (metadata engine)
    "apps.packages.apps.PackagesConfig",  # PackageEngine: validate/preview/apply/rollback (metadata plan todo 5)
    "apps.brand_experience.apps.BrandExperienceConfig",  # Bounded-context shell (metadata plan todo 2)
    "apps.runtime_blueprints.apps.RuntimeBlueprintsConfig",
    "apps.policies_rules.apps.PoliciesRulesConfig",
    "apps.plans_entitlements.apps.PlansEntitlementsConfig",
    "apps.global_registries.apps.GlobalRegistriesConfig",
    "apps.integrations_marketplace.apps.IntegrationsMarketplaceConfig",
    "apps.social_media.apps.SocialMediaConfig",
    "apps.setup_studio.apps.SetupStudioConfig",
    "apps.studio_os.apps.StudioOsConfig",
    "apps.orchestration.apps.OrchestrationConfig",  # Phase 10 — 4.1 long-running process support
    "apps.platform_runtime.apps.PlatformRuntimeConfig",  # Phase 10 — 1.2 runtime defaults (state-safe migration)
    "apps.lifecycle.apps.LifecycleConfig",  # 360 school lifecycle spine (Wave L1+)
    "emis",
    # Celery result/beat (optional: used when REDIS_URL is set for background tasks)
    "django_celery_results",
    "django_celery_beat",
    # Pass 12: CORS middleware app registration.
    "corsheaders",
]
if _channels_installed:
    INSTALLED_APPS += ["channels", "channels_redis"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Pass 12: CORS middleware must precede SessionMiddleware + CommonMiddleware per
    # django-cors-headers docs so preflight OPTIONS responses include the right headers.
    # Pass 12.C: TenantCorsAllowlistMiddleware merges per-tenant origins from
    # `school.settings["cors_allowed_origins"]` BEFORE the upstream CorsMiddleware
    # consumes the allowlist, so marketplace integrators can be added without a
    # redeploy.
    "apps.api.middleware_tenant_cors.TenantCorsAllowlistMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    # Pass 12.B: global Idempotency-Key dedupe for /api/v1/ writes; opt-in via
    # the Idempotency-Key header (Stripe / GitHub / Twilio semantics). Placed
    # after CORS so preflights aren't impacted, before everything that could
    # mutate the response.
    "apps.api.middleware_idempotency.IdempotencyKeyMiddleware",
    "config.middleware.BlockScannerPathsMiddleware",  # 404 for .git, terraform, wp-config, etc.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.accounts.middleware.ManagerCookieIsolationMiddleware",  # Manager host gets separate session/csrf cookie names
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.schools.middleware.LegacyBaseDomainRedirectMiddleware",  # Optional legacy-domain redirect middleware
    "apps.schools.middleware.UrlConfSwitcherMiddleware",  # Public vs tenant URLConf from host/path
    "apps.schools.middleware.ReservedPublicHostAccessMiddleware",  # verify./support. host isolation
    "apps.schools.middleware.PublicPathRedirectMiddleware",  # public paths hit on tenant host -> base host
    "apps.schools.middleware.TenantMiddleware",  # When USE_DJANGO_TENANTS=0: resolve request.school from host
    "apps.schools.middleware_session_school_bind.SessionSchoolBindingMiddleware",
    "apps.schools.middleware.RlsResetOnExceptionMiddleware",  # RESET app.current_school_id on response or exception
    "apps.tenancy.middleware.TenantContextMiddleware",  # Attach request.tenant_ctx (TenantContext)
    "apps.platform_runtime.middleware.TenantRuntimeMiddleware",  # Attach request.tenant_runtime (TenantRuntime)
    # v2.79: bind request.school into the email-backend thread-local so any
    # send_mail() inside this request picks up the tenant's Anymail provider
    # via PerTenantEmailBackend. Without this, per-tenant mail is only
    # honored when callers explicitly thread `school=` through, which is
    # essentially never. Clears in process_response + process_exception so
    # pooled worker threads don't leak tenants across requests.
    "apps.integrations_marketplace.middleware.TenantEmailBindingMiddleware",
    "apps.schools.middleware.TenantFreezeMiddleware",  # Section 8.6: redirect frozen schools to /account-frozen/
    "apps.schools.middleware.SentryTenantTagMiddleware",  # Phase H: tag Sentry with school_id
    "apps.schools.middleware.TenantLastActivityMiddleware",  # Phase H: optional last_activity per tenant
    "apps.schools.middleware.ModuleActivationMiddleware",  # World Engine E.2: set request.active_modules from get_tenant_modules
    "apps.schools.middleware.TenantApiQuotaMiddleware",  # Plan I: per-tenant API rate limit
    "config.middleware.GlobalHotPathRateLimitMiddleware",  # §0.3: per-IP cap on OneRoster/SCIM/LTI/token hot paths
    "config.middleware.RequestTimeoutMiddleware",  # Glocal: wall-clock cap on slow rural networks
    "apps.schools.middleware.DynamicThemeMiddleware",  # Phase B: admin theme per school (Unfold/Jazzmin/Sneat)
    "django.middleware.locale.LocaleMiddleware",  # Add for i18n
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware_session_pinning.SessionPinningMiddleware",  # Pillar 1: bind session to (IP, UA-hash); flush on mismatch
    "apps.schools.middleware_conversion_lock.ConversionLockMiddleware",
    "apps.schools.growth_funnel_middleware.GrowthFunnelMiddleware",
    "apps.schools.middleware_activation_gate.ActivationGateMiddleware",
    "apps.marketplace.middleware.AppApiContextMiddleware",  # Developer platform: app API key scope context
    "apps.accounts.middleware.ImpossibleTravelMiddleware",  # World Engine: single trigger for check_impossible_travel after login
    "apps.accounts.middleware.RoleBasedSessionTimeoutMiddleware",
    "apps.schools.middleware.ManagerHostControlPlaneRequiredMiddleware",  # manager host is platform-only beyond auth/bootstrap paths
    "apps.accounts.middleware.TenantHostControlPlaneIsolationMiddleware",  # platform operators need signed impersonation before tenant-host access
    "apps.accounts.middleware.ImpersonationReadOnlyGuardMiddleware",  # block writes on sensitive prefixes when impersonation is read-only
    "apps.schools.middleware_dashboard_topology.DashboardTopologyRBACMiddleware",
    "apps.accounts.middleware.ModuleAccessMiddleware",
    "apps.accounts.middleware.RequireMFAMiddleware",
    "apps.schools.middleware.TenantSuperAdminRequiredMiddleware",  # Restrict /super/ to SUPERADMIN
    "apps.schools.middleware.SuperAdminRateLimitMiddleware",  # 12.7: rate limit /super/ (120/min per user)
    "apps.schools.middleware_enterprise_security.EnterpriseSuperHttpAuditMiddleware",  # optional: ENTERPRISE_SUPER_HTTP_AUDIT=1
    "apps.schools.middleware.FeatureGatekeeperMiddleware",  # Phase D: enforce plan feature by path
    "apps.schools.middleware.UsageLimitMiddleware",  # Phase D (optional, on by default): Plan max_students/max_staff; set DISABLE_USAGE_LIMIT_MIDDLEWARE=1 to turn off
]
MIDDLEWARE += [
    "apps.compliance.middleware.ComplianceGuardMiddleware",  # Phase Compliance: region → feature_code RESTRICTED/DISABLED
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.ManagerTenantPrimarySurfaceBlockMiddleware",  # manager: no /studio/hubs/* or /authentication/backend/*
    "apps.siteconfig.middleware.OperatorSiteconfigManagerShellMiddleware",  # operators: tenant siteconfig URLs → manager shell
    "apps.siteconfig.middleware.MaintenanceModeMiddleware",
    "apps.siteconfig.middleware.preview_mode.PreviewModeMiddleware",
    # Phase 4: Audit & Monitoring middleware
    "apps.compliance.middleware.IPCountryAccessMiddleware",  # IP/Country access control (first!)
    "apps.compliance.middleware.AuditLoggingMiddleware",  # Log all HTTP requests
    "apps.compliance.middleware.AccessControlMiddleware",  # Enforce access control
    # Phase 5: Observability middleware (A4: request_id, tenant_id on logs)
    "apps.observability.middleware.RequestIdLoggingMiddleware",
    "apps.observability.middleware.ObservabilityMiddleware",  # Prometheus request metrics
    # Wave C — G2: count one db_session per authenticated browser session per UTC day.
    "apps.billing.middleware_metering.DBSessionMeteringMiddleware",
    # Wave E — G4: soft-log (or strict-raise) cross-region data residency mismatches.
    # Flip DATA_RESIDENCY_ENFORCE=True once region replicas are provisioned and
    # `manage.py verify_data_residency --fix-derive` has been run.
    "apps.schools.middleware_residency.DataResidencyMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Content-Security-Policy (enforced by default after v2.57 — inline-style
    # backlog hit zero per scan_inline_style_off_token CI gate, so style-src
    # 'unsafe-inline' was removed from the policy and enforce mode is now safe).
    # Operators can roll back to Report-Only via CSP_ENFORCE=0.
    "apps.security.csp_middleware.ContentSecurityPolicyMiddleware",
    # v3.33.0: paint X-RateLimit-Soft-Warn: 1 on responses whose throttle
    # crossed 80% of the scope ceiling. Reads request._rmc_rate_soft_warn
    # set inside MigrationCloudGlobalThrottle.allow_request. No-op for
    # requests where the flag isn't set, so cheap to wire globally.
    "apps.migration_cloud.api.rate_limiting.SoftWarnHeaderMiddleware",
]

# CSP defaults — enforced by default since v2.57 (inline-style backlog at 0).
# Override to Report-Only with CSP_ENFORCE=0 if a regression surfaces.
CSP_ENFORCE = os.getenv("CSP_ENFORCE", "1") == "1"

# Wave E — G4 (Gap 3, 2026-05-15): data residency enforcement toggle.
# False (default): DataResidencyMiddleware soft-logs cross-region mismatches.
# True: same middleware raises CrossRegionWriteError on mismatch, bubbling to a 500.
# Flip only after `manage.py verify_data_residency --fix-derive` is clean
# AND at least one region replica is provisioned in DATABASES.
DATA_RESIDENCY_ENFORCE = os.getenv("DATA_RESIDENCY_ENFORCE", "0") == "1"

# Wave K3 — at-risk ML artifact: where the predictor loads its joblib bundle.
# Resolution order in `apps.analytics.ml.at_risk_model`:
#   1. settings.AT_RISK_MODEL_PATH (here) — explicit override wins.
#   2. AT_RISK_MODEL_PATH env var.
#   3. Auto-discovered baseline at AT_RISK_MODEL_DIR/at_risk_v1.joblib if it exists.
# When none resolve, the heuristic baseline ships predictions instead.
AT_RISK_MODEL_DIR = os.getenv(
    "AT_RISK_MODEL_DIR", str(BASE_DIR / "var" / "at_risk")
)
_at_risk_explicit = os.getenv("AT_RISK_MODEL_PATH", "").strip()
if _at_risk_explicit:
    AT_RISK_MODEL_PATH = _at_risk_explicit
else:
    _auto_artifact = os.path.join(AT_RISK_MODEL_DIR, "at_risk_v1.joblib")
    AT_RISK_MODEL_PATH = _auto_artifact if os.path.exists(_auto_artifact) else ""

CSP_REPORT_URI = os.getenv("CSP_REPORT_URI", "/security/csp-report/")

ROOT_URLCONF = "config.urls"
PUBLIC_SCHEMA_URLCONF = "config.public_urls"
TENANT_SCHEMA_URLCONF = "config.tenant_urls"
# Django 6.0: forms.URLField default scheme becomes https; opt in to match production URLs and
# silence RemovedInDjango60Warning (e.g. platform admin webhook URL fields). Set FORMS_URLFIELD_ASSUME_HTTPS=0 to revert.
FORMS_URLFIELD_ASSUME_HTTPS = os.getenv(
    "FORMS_URLFIELD_ASSUME_HTTPS", "1"
).strip().lower() in ("1", "true", "yes")
# Keep tenant model identifiers available even in non-tenant mode; some background
# integrations import django-tenants helpers unconditionally.
TENANT_MODEL = "customers.Client"
TENANT_DOMAIN_MODEL = "customers.Domain"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.static",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "apps.siteconfig.context_processors.site_settings",
                "apps.siteconfig.email_palette.brand_email_processor",  # `brand_email` palette for emails/PDF (inline hex)
                "apps.siteconfig.platform_palette.platform_palette_processor",  # `platform_palette` for server-rendered swatch/preview defaults
                "apps.siteconfig.breadcrumb_context.breadcrumbs_context",
                "apps.siteconfig.breadcrumb_context.page_metadata_context",
                "apps.siteconfig.context_processors.region_settings",
                "apps.siteconfig.context_processors.language_context",
                "apps.siteconfig.context_processors.lexicon_context",  # Wave A — G1 tenant terminology overrides
                "apps.siteconfig.context_processors.analytics_viz_context",
                "apps.siteconfig.page_personality.personality_context_processor",  # v3.59.x Wave 11 Agent U — per-page-personality accent slug
                "apps.siteconfig.page_personality.personality_overrides_context_processor",  # v3.59.x Wave 11 Agent W — operator theme-personality CSS overrides
                "apps.siteconfig.cockpit_context.cockpit_context",  # v3.55.0 cockpit (manager only) — brand tagline + activity ticker + platform pulse + workspace context
                "apps.accounts.context_processors.dashboard_context",  # Dashboard header/footer data
                "apps.accounts.context_processors.sidebar_record_context",
                "apps.schools.context_processors.marketing_base_url",  # MARKETING_BASE_URL for cross-host links
                "apps.schools.context_processors.conversion_enforcement_context",
                "apps.schools.context_processors.operator_surface_ia_context",
                "apps.schools.context_processors.dashboard_topology_context",
                "apps.portal.context_processors.announcements",  # Global announcements banner
                "apps.portal.context_processors.platform_status_strip",  # Public-safe platform incident strip
                "apps.portal.context_processors.support_deflection_urls",  # KB deflection on all ticket forms
                "apps.portal.context_processors.help_contextual",  # Proactive help nudges + contextual drawer
                "apps.portal.context_processors.help_ai_governance",  # Parent/student AI panel policy
                "apps.lifecycle.context_processors.lifecycle_readiness",  # 360 unified score + concierge gate (Wave L3)
                "apps.feedback.context_processors.support_links",  # Host-aware help / feature / contact URLs
                "apps.siteconfig.context_processors.ai_copilot_settings",  # AI Copilot API key
                "apps.policies.context_processors.tenant_policy_context",  # tenant_ctx + global_env (Policy Registry)
                "apps.platform_runtime.context_processors.click_tracking_context",
                "apps.platform_runtime.context_processors.rum_ingest_context",
                "apps.platform_runtime.context_processors.demo_sandbox_banner",
                "apps.platform_runtime.context_processors.shell_contract_context",
                "apps.platform_runtime.context_processors.rmc_os_shell_context",
                "apps.platform_runtime.context_processors.ai_operating_layer_context",
                "apps.platform_runtime.context_processors.system_actions_context",
                "apps.platform_runtime.context_processors.offline_sync_bar_context",
                # v3.62.5 Wave 2 local-first: emits `localization` dict
                # (country_code, calendar, school_types, terminology,
                # week_start, date_format, currency_code, is_rtl) into
                # every template. Used by {% load localization %} tags +
                # by base shells emitting data-rmc-* body attrs.
                "apps.siteconfig.localization_context_processor.localization_context",
                # v3.62.10 Wave 9 local-first: emits `marketing_local` dict
                # (country_name, greeting, headline_lead, hero_subline,
                # trust_count, currency_sample, calendar_sample,
                # regulatory_line, anchor_city, regional_phrase) so the
                # marketing surface reads as written for the visitor's
                # country first, with the global frame as secondary context.
                "apps.schools.marketing_local_context.marketing_local_context",
            ]
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# ASGI Application (WebSocket / AI chat at ws/ai/chat/). Only set when channels is installed. Run with: daphne config.asgi:application or uvicorn config.asgi:application
if _channels_installed:
    ASGI_APPLICATION = "config.asgi.application"
    _redis_url = (os.getenv("REDIS_URL") or "").strip()
    if _redis_url:
        CHANNEL_LAYERS = {
            "default": {
                "BACKEND": "channels_redis.core.RedisChannelLayer",
                "CONFIG": {"hosts": [_redis_url]},
            }
        }
    else:
        CHANNEL_LAYERS = {
            "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
        }

# --- Database ---

import os
from urllib.parse import quote_plus
import dj_database_url

# unittest / manage.py test: set RMC_TEST_LOCAL_SQLITE=1 to use repo SQLite even when .env sets
# DATABASE_URL (dotenv loads after empty env; without this, tests may migrate against remote Postgres).
_RMC_TEST_LOCAL_SQLITE = RUNNING_TESTS and os.getenv(
    "RMC_TEST_LOCAL_SQLITE", ""
).strip().lower() in ("1", "true", "yes")

# Treat empty or whitespace-only as unset (avoids dj_database_url returning incomplete config)
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip() or None
if _RMC_TEST_LOCAL_SQLITE:
    DATABASE_URL = None
# Build DATABASE_URL from separate vars if set (e.g. Render injects DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT)
# Skip if DB_HOST looks like a placeholder (e.g. "from_render") and no real URL is available
if not DATABASE_URL and os.getenv("DB_HOST") and not _RMC_TEST_LOCAL_SQLITE:
    _db_host = (os.getenv("DB_HOST") or "").strip()
    if _db_host and _db_host not in ("from_render", "from_render ", ""):
        _db_user = os.getenv("DB_USER", "")
        _db_pass = os.getenv("DB_PASSWORD", "")
        _db_port = os.getenv("DB_PORT", "5432")
        _db_name = os.getenv("DB_NAME", "runmycampus_platform")
        _db_pass_enc = quote_plus(_db_pass) if _db_pass else ""
        _db_user_enc = quote_plus(_db_user) if _db_user else ""
        DATABASE_URL = f"postgresql://{_db_user_enc}:{_db_pass_enc}@{_db_host}:{_db_port}/{_db_name}"
PREVIEW_DATABASE_URL = (os.getenv("PREVIEW_DATABASE_URL") or "").strip() or None
if _RMC_TEST_LOCAL_SQLITE:
    PREVIEW_DATABASE_URL = None

if DATABASE_URL:
    _default_db = dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        ssl_require=not DEBUG,
    )
    # Ensure ENGINE is present (dj_database_url can return incomplete config if URL is malformed)
    if not _default_db.get("ENGINE"):
        _default_db["ENGINE"] = "django.db.backends.postgresql"
    DATABASES = {"default": _default_db}
else:
    # Local fallback (no DATABASE_URL) = sqlite.
    # Use DB_FILE to override path explicitly.
    # Default on Windows uses LOCALAPPDATA to avoid cloud-sync corruption under Documents.
    raw_db_file = (os.getenv("DB_FILE") or "").strip()
    if not raw_db_file:
        if os.name == "nt" and os.getenv("LOCALAPPDATA"):
            db_path = (
                Path(os.getenv("LOCALAPPDATA")) / "RunMyCampus" / "db_working.sqlite3"
            )
        else:
            db_path = BASE_DIR / "db_working.sqlite3"
    else:
        sqlite_name = os.path.expanduser(os.path.expandvars(raw_db_file))
        db_path = (
            Path(sqlite_name)
            if os.path.isabs(sqlite_name)
            else (BASE_DIR / sqlite_name)
        )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(db_path),
        }
    }

# Tests: SQLite-only runner — ignores DATABASE_URL so agents/CI don't block on unreachable Postgres.
if RUNNING_TESTS and os.getenv("RMC_SQLITE_TEST_MEMORY", "").strip().lower() in (
    "1",
    "true",
    "yes",
):
    _rmc_ts_path = BASE_DIR / ".django_test_dbs" / "rmc_sqlite_test_runner.sqlite3"
    _rmc_ts_path.parent.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(_rmc_ts_path),
            "OPTIONS": {"timeout": 90.0},
        }
    }

if PREVIEW_DATABASE_URL and not (
    RUNNING_TESTS
    and os.getenv("RMC_SQLITE_TEST_MEMORY", "").strip().lower() in ("1", "true", "yes")
):
    _preview_db = dj_database_url.config(
        default=PREVIEW_DATABASE_URL,
        conn_max_age=600,
        ssl_require=not DEBUG,
    )
    if not _preview_db.get("ENGINE"):
        _preview_db["ENGINE"] = "django.db.backends.postgresql"
    DATABASES["preview"] = _preview_db
else:
    DATABASES["preview"] = DATABASES["default"].copy()

# Wave K4 — data residency replica registration (env-driven).
#
# Operators provision a region replica without code edits by exporting
# env vars of the form ``DATA_RESIDENCY_REPLICA_<REGION>=<DATABASE_URL>``.
# Each one registers a ``replica_<region>`` alias in DATABASES that
# downstream routers / verification commands can target.
#
# Examples:
#   DATA_RESIDENCY_REPLICA_EU_CENTRAL=postgres://user:pw@eu-host/db
#   DATA_RESIDENCY_REPLICA_UK=postgres://user:pw@uk-host/db
#
# Skipped during tests so the SQLite test runner doesn't try to mount
# unreachable Postgres replicas in CI.
DATA_RESIDENCY_REPLICA_ALIASES: dict[str, str] = {}
if not RUNNING_TESTS:
    _PREFIX = "DATA_RESIDENCY_REPLICA_"
    for _env_key, _env_val in os.environ.items():
        if not _env_key.startswith(_PREFIX):
            continue
        _region = _env_key[len(_PREFIX):].strip().lower()
        _url = (_env_val or "").strip()
        if not _region or not _url:
            continue
        _alias = f"replica_{_region}"
        try:
            _replica_db = dj_database_url.config(
                default=_url, conn_max_age=600, ssl_require=not DEBUG
            )
        except Exception:  # noqa: BLE001 — bad URL: skip, don't crash boot
            continue
        if not _replica_db.get("ENGINE"):
            _replica_db["ENGINE"] = "django.db.backends.postgresql"
        DATABASES[_alias] = _replica_db
        DATA_RESIDENCY_REPLICA_ALIASES[_region] = _alias

# When running tests with SQLite and preview is a copy of default, use only default
# to avoid Django cloning the test DB and re-running migrations (duplicate column errors).
if (
    not PREVIEW_DATABASE_URL
    and RUNNING_TESTS
    and DATABASES.get("default", {}).get("ENGINE") == "django.db.backends.sqlite3"
):
    DATABASES = {"default": DATABASES["default"]}

# Release gate (LOCKED STABLE): full `manage.py test` + verifier bundle + smoke;
# see docs/deployment/RELEASE_TEST_POLICY.md.
#
# Django defaults sqlite test databases to in-memory databases when no explicit
# TEST NAME is provided. That makes `--keepdb` ineffective across separate
# manage.py invocations, because each process rebuilds the full test schema.
# Force file-backed sqlite test DBs so repeated local test runs can reuse the
# migrated schema and avoid multi-minute bootstrap penalties.
_sqlite_test_db_dir = BASE_DIR / ".django_test_dbs"
for _alias, _db_config in DATABASES.items():
    if _db_config.get("ENGINE") != "django.db.backends.sqlite3":
        continue
    _sqlite_test_db_dir.mkdir(parents=True, exist_ok=True)
    _test_name_env = (
        "DJANGO_TEST_DB_FILE"
        if _alias == "default"
        else f"DJANGO_{_alias.upper()}_TEST_DB_FILE"
    )
    _test_name_default = _sqlite_test_db_dir / f"{_alias}.sqlite3"
    _test_name_raw = (os.getenv(_test_name_env) or "").strip()
    _test_name = Path(_test_name_raw) if _test_name_raw else _test_name_default
    if not _test_name.is_absolute():
        _test_name = BASE_DIR / _test_name
    _test_name.parent.mkdir(parents=True, exist_ok=True)
    _db_config.setdefault("TEST", {})
    _db_config["TEST"]["NAME"] = str(_test_name)
    # Busy timeout (seconds) for sqlite3.connect — reduces flaky "database is locked"
    # on Windows when many tests hit the same file-backed test DB (--keepdb).
    _db_config.setdefault("OPTIONS", {})
    _db_config["OPTIONS"].setdefault("timeout", 30.0)

# Optional: use SQLite :memory: for TEST NAME only (can be flaky on some Windows setups).
if RUNNING_TESTS and os.getenv("RMC_SQLITE_TEST_USE_MEMORY_NAME", "").strip().lower() in (
    "1",
    "true",
    "yes",
):
    for _db_config in DATABASES.values():
        if _db_config.get("ENGINE") == "django.db.backends.sqlite3":
            _db_config.setdefault("TEST", {})
            _db_config["TEST"]["NAME"] = ":memory:"

# Longer busy timeout during unittest / manage.py test reduces flaky "database is locked" on
# Windows with file-backed SQLite + --keepdb (pre_deploy_gate, local agents).
if RUNNING_TESTS:
    for _db_config in DATABASES.values():
        if _db_config.get("ENGINE") == "django.db.backends.sqlite3":
            _opts = _db_config.setdefault("OPTIONS", {})
            _opts["timeout"] = max(float(_opts.get("timeout", 30.0)), 90.0)

# PERFORMANCE: Enable persistent database connections (600 seconds = 10 minutes)
# Reduces overhead of creating new connection for each request
for db_config in DATABASES.values():
    db_config["CONN_MAX_AGE"] = 600

# Tests + SQLite: persistent connections worsen "database is locked" on Windows when
# using file-backed test DBs (--keepdb, DJANGO_TEST_DB_FILE). Release after each request.
if RUNNING_TESTS:
    for db_config in DATABASES.values():
        if db_config.get("ENGINE") == "django.db.backends.sqlite3":
            db_config["CONN_MAX_AGE"] = 0

DATABASE_ROUTERS = [
    "apps.siteconfig.db_router.TenantDatabaseRouter",
    "apps.siteconfig.db_router.PreviewDatabaseRouter",
]

MARKSHEET_OCR_COMMAND = os.getenv("MARKSHEET_OCR_COMMAND", "")


AUTH_USER_MODEL = "accounts.User"

# --- Authentication backends ---
# LegacyHashUpgradeBackend runs FIRST so that users migrated in from
# PowerSchool / Blackbaud / Veracross / FACTS / Skyward / Alma can sign
# in with their existing passwords. On first match it re-hashes to the
# native PASSWORD_HASHERS chain and clears the foreign hash atomically.
# The standard ModelBackend stays in the list to handle native users.
AUTHENTICATION_BACKENDS = [
    "apps.accounts.auth_backends_legacy.LegacyHashUpgradeBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# --- Password hashing ---
# Argon2 first (memory-hard, OWASP-recommended for new deployments).
# PBKDF2 + BCrypt remain in the list so existing hashes verify; Django auto-
# upgrades a user to Argon2 on their next successful login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# --- Migration-cloud "password preservation moat" encryption key ---
# Used by apps.accounts.legacy_hashes.encryption to encrypt the three
# legacy_* User columns at rest. In production set DJANGO_CRYPTOGRAPHY_KEY
# to a freshly generated Fernet key (Python: ``from cryptography.fernet
# import Fernet; print(Fernet.generate_key().decode())``). If unset, the
# encryption helper derives a key deterministically from SECRET_KEY
# (development convenience; rotating SECRET_KEY breaks decryption of
# existing rows — production deployments must set the env var
# explicitly). The CRYPTOGRAPHY_KEY name is also what the upstream
# django-cryptography 1.x reads when its conf is initialized.
CRYPTOGRAPHY_KEY = os.environ.get("DJANGO_CRYPTOGRAPHY_KEY") or SECRET_KEY

# --- Migration Cloud MAA version flip (v3.34.0 Agent 5) ---
# Promotion plumbing for the MAA v2.0 counsel-pending body. We CANNOT
# promote v2.0 to default until external counsel signs off — that step
# is a real-world legal deferral, not a software change. What this
# setting does ship is the **one-config-flip** wiring so that when
# counsel signoff lands the operator can advance the default with a
# single env-var change (plus a maa_text.py edit that removes "v2.0"
# from the draft-version set). See
# ``docs/MAA_V2_PROMOTION_CHECKLIST.md`` for the full procedure.
#
# Safety contract:
#   * Default value is "v1.0" — the production-signed body. Never
#     auto-flips. Operators must explicitly set the env var to promote.
#   * Opt-in tenants (RMC_MAA_V2_OPTIN_TENANT_IDS) get a **preview-only**
#     v2.0 banner in the sign flow. The signature_text captured at
#     server-side is STILL the active version — preview never binds.
#   * The active version that the receiver signs is resolved via
#     ``apps.migration_cloud.services.maa_text.resolve_active_version_for_tenant``;
#     the preview version (if any) is resolved via
#     ``resolve_preview_version_for_tenant``.
MIGRATION_CLOUD_MAA_DEFAULT_VERSION = os.environ.get(
    "RMC_MAA_DEFAULT_VERSION", "v1.0"
)
MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS = [
    int(_x)
    for _x in (os.environ.get("RMC_MAA_V2_OPTIN_TENANT_IDS", "") or "").split(",")
    if _x.strip().isdigit()
]

# --- Celery beat enablement gate (v3.34.0 Agent 5) ---
# Lazy guard for beat entries that the operator can defer per-environment
# (e.g. local dev should not poll upstream PyPI for django-cryptography
# every Monday). Production sets this to "1"; CI / dev lanes default
# off via the env. Existing beat entries that predate this setting
# remain active unconditionally — only entries that explicitly check
# this flag are gated.
CELERY_BEAT_ENABLED = (
    os.environ.get("CELERY_BEAT_ENABLED", "1").strip() == "1"
)

# --- Static / Media ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Part F 16.4 / 16.6: Global edge and testing matrix (docs/architecture/global_edge_and_testing_matrix.md)
EDGE_REGION_HEADER = os.getenv("EDGE_REGION_HEADER", "HTTP_X_REGION")
CDN_BASE_URL = (os.getenv("CDN_BASE_URL") or "").strip() or ""
TESTING_MATRIX_REGIONS = [
    "US",
    "BR",
    "DE",
    "JP",
    "NG",
    "AE",
    "CA",
    "GB",
]  # USA, Brazil, Germany, Japan, Nigeria, UAE, Canada, UK

# --- Authentication ---
LOGIN_URL = "/authentication/login/"
LOGIN_REDIRECT_URL = "/authentication/redirect/"
LOGOUT_REDIRECT_URL = "/authentication/login/"

# Security Powerhouse (plan 3.21): Account locking after 5 failed attempts.
# Install: pip install django-defender. Set DEFENDER_ENABLED=1 to enable.
DEFENDER_ENABLED = os.getenv("DEFENDER_ENABLED", "0") in ("1", "true", "yes")
if DEFENDER_ENABLED:
    try:
        __import__("defender")
    except ImportError:
        DEFENDER_ENABLED = False
if DEFENDER_ENABLED:
    DEFENDER_DISABLE_GET_LOGIN = False
    DEFENDER_GET_USERNAME_FROM_REQUEST_PATH = (
        "apps.accounts.defender_utils.get_username_from_request"
    )
    DEFENDER_LOCK_OUT_BY_IP_OR_USERNAME = True
    DEFENDER_BEHIND_REVERSE_PROXY = os.getenv("RENDER", "0") == "1"
    DEFENDER_FAILURE_LIMIT = 5
    DEFENDER_COOLOFF_TIME = 60 * 15  # 15 minutes
    DEFENDER_DISABLE_IP_LOCKOUT = False
    INSTALLED_APPS.append("defender")
    _auth_idx = next(
        (i for i, m in enumerate(MIDDLEWARE) if "AuthenticationMiddleware" in m),
        len(MIDDLEWARE),
    )
    MIDDLEWARE.insert(_auth_idx, "defender.middleware.FailedLoginMiddleware")

# --- Site behavior ---
MAINTENANCE_MODE = False

# --- Metadata: Batch 14 legacy siteconfig DynamicField* bridge (retired Phase 5b) ---
# siteconfig.0168 removed siteconfig_dynamicfield*; these flags are kept as no-ops for
# env compatibility. Do not enable — fallback/dual-read/write paths were deleted.
METADATA_DYNAMICFIELD_SITECONFIG_FALLBACK = False
METADATA_DYNAMICFIELD_DUAL_WRITE_FROM_SITECONFIG = False

# Render terminates TLS at the edge. Internal platform probes may hit HTTP
# without X-Forwarded-Proto and get redirected, which can break startup scans.
_secure_ssl_redirect_default = "0" if _is_render else "1"
SECURE_SSL_REDIRECT = (
    os.getenv("SECURE_SSL_REDIRECT", _secure_ssl_redirect_default) == "1" and not DEBUG
)
# Test runner uses plain HTTP requests; keep HTTPS redirect behavior for runtime envs.
if RUNNING_TESTS:
    SECURE_SSL_REDIRECT = False

# Serial DiscoverRunner + aggressive SQLite connection cleanup (scripts/run_full_test_suite.*).
# Opt out: RMC_RELIABLE_TEST_RUNNER=0  OR  DJANGO_TEST_RUNNER=django.test.runner.DiscoverRunner
if RUNNING_TESTS:
    _test_runner_env = os.getenv("DJANGO_TEST_RUNNER", "").strip()
    if _test_runner_env:
        TEST_RUNNER = _test_runner_env
    elif os.getenv("RMC_RELIABLE_TEST_RUNNER", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ):
        TEST_RUNNER = "config.reliable_test_runner.ReliableDiscoverRunner"
# Health/readiness probes can come over plain HTTP from platform internals.
# Exempt these endpoints to avoid redirect loops and failed boot probes.
SECURE_REDIRECT_EXEMPT = [
    r"^$",
    r"^health/",
    r"^healthz/",
    r"^ready/",
    r"^status/",
    r"^api/health/",
    r"^api/caddy-check/",  # Section 8: Caddy on-demand TLS (often called over HTTP by Caddy)
    r"^discover/",  # Section 8: Global login discovery (landing page)
    r"^account-frozen/",  # Section 8: Frozen account page (may be hit before HTTPS)
]
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "1") == "1" and not DEBUG
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "1") == "1" and not DEBUG
if RUNNING_TESTS:
    # Django test Client uses HTTP; Secure cookies would never round-trip.
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
# Cookies must not be readable by JavaScript — defense-in-depth for XSS.
SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "1") == "1"
CSRF_COOKIE_HTTPONLY = os.getenv("CSRF_COOKIE_HTTPONLY", "1") == "1"
# HSTS: 60s is too short for any real protection. Default to 1 year in production
# so a single MITM cannot strip HTTPS within an hour. Leave 0 in DEBUG (local dev).
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000")) if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "1") == "1"
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "1") == "1"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
# Clickjacking + referrer protection. Marketing pages may need SAMEORIGIN
# (e.g. for embedded demos); operators can override per host.
X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "DENY")
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
_secure_coop = os.getenv("SECURE_CROSS_ORIGIN_OPENER_POLICY", "").strip() or "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = _secure_coop
# Cross-Origin-Resource-Policy mitigates Spectre-class side-channel reads.
_secure_corp = os.getenv("SECURE_CROSS_ORIGIN_RESOURCE_POLICY", "").strip() or "same-site"
SECURE_CROSS_ORIGIN_RESOURCE_POLICY = _secure_corp
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
MANAGER_SESSION_COOKIE_NAME = (
    os.getenv("MANAGER_SESSION_COOKIE_NAME") or "rmc_manager_sessionid"
).strip()
MANAGER_CSRF_COOKIE_NAME = (
    os.getenv("MANAGER_CSRF_COOKIE_NAME") or "rmc_manager_csrftoken"
).strip()
_session_cookie_domain_env = (os.getenv("SESSION_COOKIE_DOMAIN") or "").strip()
if _session_cookie_domain_env:
    SESSION_COOKIE_DOMAIN = _session_cookie_domain_env
_csrf_cookie_domain_env = (os.getenv("CSRF_COOKIE_DOMAIN") or "").strip()
if _csrf_cookie_domain_env:
    CSRF_COOKIE_DOMAIN = _csrf_cookie_domain_env
_manager_session_cookie_domain_env = (
    os.getenv("MANAGER_SESSION_COOKIE_DOMAIN") or ""
).strip()
MANAGER_SESSION_COOKIE_DOMAIN = _manager_session_cookie_domain_env or None
_manager_csrf_cookie_domain_env = (
    os.getenv("MANAGER_CSRF_COOKIE_DOMAIN") or ""
).strip()
MANAGER_CSRF_COOKIE_DOMAIN = _manager_csrf_cookie_domain_env or None

# Signed impersonation token TTL (seconds); must match unsign max_age on tenant consume.
IMPERSONATION_TOKEN_MAX_AGE_SECONDS = int(
    os.getenv("IMPERSONATION_TOKEN_MAX_AGE_SECONDS", "3600")
)
# When true, switch_to_tenant requires a non-empty justification (POST impersonation_reason).
IMPERSONATION_REQUIRE_JUSTIFICATION = (
    os.getenv("IMPERSONATION_REQUIRE_JUSTIFICATION", "1").strip().lower()
    in {"1", "true", "yes"}
)
# Default for new impersonation tokens: read-only until operator checks “allow writes”.
IMPERSONATION_DEFAULT_READ_ONLY = (
    os.getenv("IMPERSONATION_DEFAULT_READ_ONLY", "1").strip().lower()
    in {"1", "true", "yes"}
)
# Log mutating /super/ requests to compliance AuditLog (see middleware_enterprise_security).
ENTERPRISE_SUPER_HTTP_AUDIT = (
    os.getenv("ENTERPRISE_SUPER_HTTP_AUDIT", "0").strip().lower()
    in {"1", "true", "yes"}
)
# Prefixes blocked for POST/PUT/PATCH/DELETE while impersonation session has read_only=True.
IMPERSONATION_READ_ONLY_BLOCKED_WRITE_PREFIXES = (
    "/admin/",
    "/api/",
    "/finance/",
    "/evals/",
    "/people/",
    "/academics/",
    "/communication/",
    "/reports/",
    "/portal/",
    "/studio/",
    "/siteconfig/",
    "/requests/",
    "/payroll/",
    "/analytics/",
    "/compliance/",
)

# Manager and tenant planes use host-only cookies unless domains are set.
# “Open as school” (manager → tenant impersonation) requires the browser to send the same
# session to both hosts: set SESSION_COOKIE_DOMAIN and CSRF_COOKIE_DOMAIN to the parent
# (e.g. .runmycampus.com) and align MANAGER_SESSION_COOKIE_DOMAIN / MANAGER_CSRF_COOKIE_DOMAIN
# so manager.* and *.tenant share cookies. Otherwise operators must log in again on the tenant.
# Set SESSION_COOKIE_DOMAIN / CSRF_COOKIE_DOMAIN explicitly only when you accept shared auth scope.
# Session expiry: use SESSION_INACTIVITY_TIMEOUT_MINUTES for shared computers (e.g. 15–30),
# or SESSION_COOKIE_AGE (seconds) for max session length. With SESSION_SAVE_EVERY_REQUEST=True,
# session expires after this many seconds of *inactivity* (no requests).
_session_inactivity_minutes = os.getenv("SESSION_INACTIVITY_TIMEOUT_MINUTES", "")
if _session_inactivity_minutes.strip():
    SESSION_COOKIE_AGE = int(_session_inactivity_minutes) * 60
else:
    SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "14400"))  # 4 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = (
    os.getenv("SESSION_EXPIRE_AT_BROWSER_CLOSE", "1") == "1"
)
SESSION_SAVE_EVERY_REQUEST = os.getenv("SESSION_SAVE_EVERY_REQUEST", "1") == "1"

# Marketing (Plan 4.11): demo tenant URL for "Try demo" CTA; analytics script URL for marketing pages
# TENANT_EXAMPLE_SLUG: e.g. demo-school — used for example tenant links in marketing copy and, when
# MARKETING_DEMO_TENANT_URL is unset, to build https://{slug}.{MULTI_TENANT_BASE_DOMAIN}/
_tenant_example_slug_raw = (os.getenv("TENANT_EXAMPLE_SLUG") or "").strip()
TENANT_EXAMPLE_SLUG = _tenant_example_slug_raw or None
MARKETING_KB_TENANT_SLUG = (
    (os.getenv("MARKETING_KB_TENANT_SLUG") or "").strip()
    or TENANT_EXAMPLE_SLUG
    or "demo-school"
)
MARKETING_DEMO_TENANT_URL = derive_marketing_demo_tenant_url(
    os.getenv("MARKETING_DEMO_TENANT_URL") or "",
    TENANT_EXAMPLE_SLUG,
    _multi_tenant_base,
)
# Tenant UI: show a non-dismissible demo banner on authenticated portal/backend surfaces.
RUNMYCAMPUS_DEMO_SANDBOX = os.getenv("RUNMYCAMPUS_DEMO_SANDBOX", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
# Enterprise demo mode: same banner + guided hints; also accept RUNMYCAMPUS_DEMO_MODE or DEMO_MODE.
RUNMYCAMPUS_DEMO_MODE = os.getenv("RUNMYCAMPUS_DEMO_MODE", "").strip().lower() in (
    "1",
    "true",
    "yes",
) or os.getenv("DEMO_MODE", "").strip().lower() in ("1", "true", "yes")
# Unified flag for templates (sandbox OR explicit demo mode).
RUNMYCAMPUS_DEMO_ENABLED = RUNMYCAMPUS_DEMO_SANDBOX or RUNMYCAMPUS_DEMO_MODE
# Tenant ADMIN activation landing after self-service signup verify (school.settings.rmc_activation_gate).
DISABLE_SCHOOL_ACTIVATION_GATE = os.getenv(
    "DISABLE_SCHOOL_ACTIVATION_GATE", ""
).strip().lower() in ("1", "true", "yes")
# Conversion lock (apps.schools.middleware_conversion_lock): blocks tenant routes until first_action_completed.
# Production / staging / cloud host: strict ON. Local dev (DEBUG=1, not Render, not RMC_ENV): permissive.
# Override with CONVERSION_LOCK_STRICT=0.
_default_conversion_strict = (
    "" if RUNNING_TESTS else ("1" if ((not DEBUG) or _IS_CLOUD_DEPLOYED) else "")
)
CONVERSION_LOCK_STRICT = (
    os.getenv("CONVERSION_LOCK_STRICT", _default_conversion_strict).strip().lower()
    in ("1", "true", "yes")
)
# If True with CONVERSION_LOCK_STRICT, every tenant without first_action_completed is locked.
_default_conversion_all = "1" if CONVERSION_LOCK_STRICT else ""
CONVERSION_LOCK_ALL_SCHOOLS = (
    os.getenv("CONVERSION_LOCK_ALL_SCHOOLS", _default_conversion_all).strip().lower()
    in ("1", "true", "yes")
)
# Use granular workflow prefixes (not full /portal/) so dashboards stay blocked until first action.
_default_narrow = "1" if CONVERSION_LOCK_STRICT else ""
CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS = (
    os.getenv("CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS", _default_narrow).strip().lower()
    in ("1", "true", "yes")
)
# Extra path prefixes (tuple of strings) appended to base allowlist in conversion_lock_paths.
CONVERSION_LOCK_ALLOWED_PREFIXES: tuple[str, ...] = tuple(
    p.strip()
    for p in (os.getenv("CONVERSION_LOCK_ALLOWED_PREFIXES") or "").split(",")
    if p.strip()
)
# Action strip: force at most one primary system action when True.
_default_single_action = "1" if CONVERSION_LOCK_STRICT else ""
CONVERSION_SINGLE_ACTION_ENFORCED = (
    os.getenv(
        "CONVERSION_SINGLE_ACTION_ENFORCED", _default_single_action
    ).strip().lower()
    in ("1", "true", "yes")
)
# Activation landing: allow "Skip for now" (escape hatch). Strict default: dismiss OFF in production.
_default_allow_dismiss = "" if CONVERSION_LOCK_STRICT else "1"
ACTIVATION_GATE_ALLOW_DISMISS = (
    os.getenv("ACTIVATION_GATE_ALLOW_DISMISS", _default_allow_dismiss).strip().lower()
    in ("1", "true", "yes")
)
# Tests: never force strict marketplace/conversion (override_settings still works for explicit tests).
if RUNNING_TESTS:
    CONVERSION_LOCK_STRICT = False
    CONVERSION_LOCK_ALL_SCHOOLS = False
    CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS = False
    CONVERSION_SINGLE_ACTION_ENFORCED = False
    ACTIVATION_GATE_ALLOW_DISMISS = True
    MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING = False
# Metrics governance: never claim ≥50% click reduction unless this is explicitly enabled with evidence.
FIFTY_PCT_REDUCTION_CLAIM_ALLOWED = os.getenv(
    "FIFTY_PCT_REDUCTION_CLAIM_ALLOWED", ""
).strip().lower() in ("1", "true", "yes")
MARKETING_ANALYTICS_SCRIPT_URL = (
    os.getenv("MARKETING_ANALYTICS_SCRIPT_URL") or ""
).strip() or ""
MARKETING_ANALYTICS_ENDPOINT_URL = (
    os.getenv("MARKETING_ANALYTICS_ENDPOINT_URL") or ""
).strip() or ""
# Optional: regional / campaign JSON layers — compare_eu.json, pricing_us.json, slug_variant.json, etc.
_mkt_region = (os.getenv("MARKETING_CONTENT_REGION") or "").strip().lower()
_mkt_variant = (os.getenv("MARKETING_CONTENT_VARIANT") or "").strip().lower()
MARKETING_CONTENT_REGION = _mkt_region or None
MARKETING_CONTENT_VARIANT = _mkt_variant or None
# A/B landing: optional override text appended for hero_variant "B" when CMS landing_hero_ai_line is unset.
MARKETING_HERO_VARIANT_B_SUBLINE = (
    (os.getenv("MARKETING_HERO_VARIANT_B_SUBLINE") or "").strip() or None
)
# Marketing visual assets (override via env for production; fallbacks in apps/schools/marketing_views.py).
# Full list of optional keys: MARKETING_PROOF_HERO_IMAGE_KEY, MARKETING_MIGRATION_DIAGRAM_URL, MARKETING_ECOSYSTEM_DIAGRAM_URL,
# MARKETING_CONTROL_PLANE_DIAGRAM_URL, MARKETING_SETUP_STUDIO_FLOW_IMAGE_URL, MARKETING_HEALTH_SCORE_VISUAL_URL,
# MARKETING_ROLE_PREVIEW_IMAGES, MARKETING_GLOBAL_MAP_IMAGE_URL, MARKETING_ILLUSTRATION_*, MARKETING_PRODUCT_VISUALIZATION_SLIDES.
# See docs/MARKETING_FRONT_PLACEHOLDER.md and marketing_views._marketing_context for all keys.
MARKETING_VERB_NAV_ENABLED = os.getenv("MARKETING_VERB_NAV_ENABLED", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
MARKETING_HERO_IMAGE_URL = (os.getenv("MARKETING_HERO_IMAGE_URL") or "").strip() or None
MARKETING_HERO_VIDEO_URL = (os.getenv("MARKETING_HERO_VIDEO_URL") or "").strip() or None
MARKETING_HERO_VIDEO_POSTER_URL = (
    os.getenv("MARKETING_HERO_VIDEO_POSTER_URL") or ""
).strip() or None
# Optional overrides for marketing_ai.get_marketing_ai_asset_url (same keys as MARKETING_AI_ASSET_KEYS).
MARKETING_MIGRATION_FLOW_IMAGE_URL = (
    os.getenv("MARKETING_MIGRATION_FLOW_IMAGE_URL") or ""
).strip() or None
MARKETING_SETUP_STUDIO_IMAGE_URL = (
    os.getenv("MARKETING_SETUP_STUDIO_IMAGE_URL") or ""
).strip() or None
MARKETING_ECOSYSTEM_IMAGE_URL = (
    os.getenv("MARKETING_ECOSYSTEM_IMAGE_URL") or ""
).strip() or None
MARKETING_MARKETPLACE_IMAGE_URL = (
    os.getenv("MARKETING_MARKETPLACE_IMAGE_URL") or ""
).strip() or None
MARKETING_MIGRATION_STUDIO_IMAGE_URL = (
    os.getenv("MARKETING_MIGRATION_STUDIO_IMAGE_URL") or ""
).strip() or None
MARKETING_MIGRATION_CLOUD_DIAGRAM_URL = (
    os.getenv("MARKETING_MIGRATION_CLOUD_DIAGRAM_URL") or ""
).strip() or None
MARKETING_PLATFORM_ARCHITECTURE_DIAGRAM_URL = (
    os.getenv("MARKETING_PLATFORM_ARCHITECTURE_DIAGRAM_URL") or ""
).strip() or None
MARKETING_SCHOOL_IN_A_BOX_FLOW_IMAGE_URL = (
    os.getenv("MARKETING_SCHOOL_IN_A_BOX_FLOW_IMAGE_URL") or ""
).strip() or None
MARKETING_DATA_INTELLIGENCE_LOOP_IMAGE_URL = (
    os.getenv("MARKETING_DATA_INTELLIGENCE_LOOP_IMAGE_URL") or ""
).strip() or None
MARKETING_ECOSYSTEM_MAP_IMAGE_URL = (
    os.getenv("MARKETING_ECOSYSTEM_MAP_IMAGE_URL") or ""
).strip() or None
MARKETING_STATUS_PAGE_URL = (
    os.getenv("MARKETING_STATUS_PAGE_URL") or ""
).strip() or None
MARKETING_CALENDLY_URL = (os.getenv("MARKETING_CALENDLY_URL") or "").strip() or None
# Optional inbound webhooks for marketing forms (POST JSON). Contact form prefers CONTACT then DEMO URL.
MARKETING_DEMO_WEBHOOK_URL = (
    (os.getenv("MARKETING_DEMO_WEBHOOK_URL") or "").strip() or None
)
MARKETING_CONTACT_WEBHOOK_URL = (
    (os.getenv("MARKETING_CONTACT_WEBHOOK_URL") or "").strip() or None
)
# Demo page: "What you'll see" bullets (required); set MARKETING_DEMO_WHAT_YOU_SEE as JSON array or comma-separated in env
_demo_what = os.getenv("MARKETING_DEMO_WHAT_YOU_SEE", "").strip()
if _demo_what:
    try:
        import json

        MARKETING_DEMO_WHAT_YOU_SEE = (
            json.loads(_demo_what)
            if _demo_what.startswith("[")
            else [s.strip() for s in _demo_what.split(",") if s.strip()]
        )
    except (ValueError, TypeError):
        # JSONDecodeError is a subclass of ValueError; fallback to comma-separated parse
        MARKETING_DEMO_WHAT_YOU_SEE = [
            s.strip() for s in _demo_what.split(",") if s.strip()
        ]
else:
    MARKETING_DEMO_WHAT_YOU_SEE = [
        "Public marketing and discovery experience",
        "Tenant login and school dashboard",
        "Manager control plane and command center",
    ]
# Product tour: URL for "Click through the platform" (Navattic, Product Fruits, or internal interactive preview)
MARKETING_PRODUCT_TOUR_URL = (
    os.getenv("MARKETING_PRODUCT_TOUR_URL") or ""
).strip() or None
# Newsletter: form action URL (POST); required for signup (set to your list endpoint or webhook)
MARKETING_NEWSLETTER_FORM_ACTION = (
    os.getenv("MARKETING_NEWSLETTER_FORM_ACTION") or ""
).strip() or None
# §8 replacement messaging: comparison table rows and replacement copy (apps/schools/marketing_views context)
# Set via settings or env JSON. See MARKETING_FRONT_PLACEHOLDER.md. Placeholder when env unset so templates can iterate safely.
import json as _json


def _safe_mkt_json_list(env_val: str, default: list) -> list:
    """Parse env JSON list for §8 MARKETING_*; return default on invalid or empty."""
    s = (env_val or "").strip()
    if not s or not s.startswith("["):
        return default
    try:
        out = _json.loads(s)
        return out if isinstance(out, list) else default
    except (ValueError, TypeError, _json.JSONDecodeError):
        return default


def _safe_mkt_json_dict(env_val: str, default: dict) -> dict:
    """Parse env JSON dict for §8 MARKETING_*; return default on invalid or empty."""
    s = (env_val or "").strip()
    if not s or not s.startswith("{"):
        return default
    try:
        out = _json.loads(s)
        return out if isinstance(out, dict) else default
    except (ValueError, TypeError, _json.JSONDecodeError):
        return default


_mkt_comparison = (os.getenv("MARKETING_COMPARISON_TABLE") or "").strip()
MARKETING_COMPARISON_TABLE = _safe_mkt_json_list(
    _mkt_comparison,
    [{"feature": "Platform", "runmycampus": "RunMyCampus", "other": "Other"}],
)
_mkt_replacement = (os.getenv("MARKETING_REPLACEMENT_MESSAGING") or "").strip()
MARKETING_REPLACEMENT_MESSAGING = _safe_mkt_json_dict(
    _mkt_replacement,
    {
        "headline": "Switch with confidence",
        "subline": "Replace legacy systems with one platform.",
    },
)

# Role-based session overrides (seconds)
ROLE_SESSION_TIMEOUTS = {
    "SUPERADMIN": int(os.getenv("SESSION_TIMEOUT_SUPERADMIN", "1800")),  # 30 min
    "ADMIN": int(os.getenv("SESSION_TIMEOUT_ADMIN", "1800")),  # 30 min
    "DEPT_LEAD": int(os.getenv("SESSION_TIMEOUT_DEPT_LEAD", "3600")),  # 1 hr
    "FINANCE_STAFF": int(os.getenv("SESSION_TIMEOUT_FINANCE_STAFF", "3600")),  # 1 hr
    "IT_ADMIN": int(os.getenv("SESSION_TIMEOUT_IT_ADMIN", "3600")),  # 1 hr
    "TEACHER": int(os.getenv("SESSION_TIMEOUT_TEACHER", "14400")),  # 4 hr
    "PARENT": int(os.getenv("SESSION_TIMEOUT_PARENT", "21600")),  # 6 hr
    "STUDENT": int(os.getenv("SESSION_TIMEOUT_STUDENT", "21600")),  # 6 hr
}

# --- Admin theme (Unfold) ---
# Docs: https://unfoldadmin.com/docs/configuration/settings/
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

UNFOLD = {
    "SITE_TITLE": "RunMyCampus Admin",
    "SITE_HEADER": "RunMyCampus",
    "SITE_SUBHEADER": "",  # Single-line brand only; no tagline in admin/sidebar
    "SITE_URL": "/",
    # Icon/branding (32px height works best); platform uses RunMyCampus icon
    "SITE_ICON": lambda request: static("images/runmycampus-icon.png"),
    # Small UX improvements
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SHOW_BACK_BUTTON": True,
    # Titles
    "ENVIRONMENT": "Development" if DEBUG else "Production",
    # Sidebar: search, all-apps dropdown; collapsible app groups in app_list.html
    "SIDEBAR": {
        "show_search": True,
        "command_search": False,
        "show_all_applications": True,
        "navigation": [],
    },
    # Phase H: Bento-style admin index; injects school logo/colors when request.school is set
    "DASHBOARD_CALLBACK": "apps.siteconfig.unfold_dashboard.dashboard_callback",
    # Custom CSS (theme-proof, sidebar scroll, dashboard) loaded via admin/base_site.html extrastyle
}

# --- Logging (configured below in "Logging Configuration" section) ---

# --- Webhook Security Configuration ---
WEBHOOK_CONFIG = {
    "rate_limit": int(os.getenv("WEBHOOK_RATE_LIMIT", "100")),  # requests per minute
    "signature_algorithm": os.getenv("WEBHOOK_SIGNATURE_ALGORITHM", "sha256"),
    "signature_header": os.getenv("WEBHOOK_SIGNATURE_HEADER", "X-Signature"),
    "ip_whitelist": os.getenv("WEBHOOK_IP_WHITELIST", "").split(",")
    if os.getenv("WEBHOOK_IP_WHITELIST")
    else [],
}

# --- Observability ---
OBSERVABILITY_API_KEY = os.getenv("OBSERVABILITY_API_KEY", "")

# --- Policy / Marketplace (Phase 7, 24.12) — non-negotiable, always on ---
# When True, get_effective_policy merges from TenantBlueprint.active_bundle.policy_snapshot when set. Required; default on.
POLICY_USE_BUNDLES = os.getenv("POLICY_USE_BUNDLES", "1") in ("1", "true", "yes")
# Move 3 follow-up: PDP runtime enforcement mode.
#   "off"      — PDP decorators short-circuit; no log, no block.
#   "advisory" — every PDP-decorated view calls decide() and writes a
#                PolicyDecisionLog row but never raises. Safe default; use
#                this to collect would-be denies before flipping to enforce.
#   "enforce"  — pdp_enforce decorators block on deny / implicit_deny;
#                pdp_advisory still logs.
POLICY_PDP_ENFORCEMENT_MODE = os.getenv("POLICY_PDP_ENFORCEMENT_MODE", "advisory")
# Per-tenant policy cache TTL in seconds. Required for scale; default 300 (5 min). Set POLICY_CACHE_TTL=0 to disable for debugging.
_raw_ttl = os.getenv("POLICY_CACHE_TTL", "300").strip()
POLICY_CACHE_TTL = int(_raw_ttl) if _raw_ttl.isdigit() else 300
if POLICY_CACHE_TTL < 0:
    POLICY_CACHE_TTL = 300
# 24.12: Third-party apps may run schema patches only for these Django app labels (tuple). Empty = none.
_THIRD_PARTY_ALLOWLIST_RAW = (
    os.getenv("THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST") or ""
).strip()
THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST = tuple(
    s.strip() for s in _THIRD_PARTY_ALLOWLIST_RAW.split(",") if s.strip()
)

# --- Payment Provider Configuration ---
# Each provider should have config in PaymentIntegration model:
# {
#     "webhook_secret": "api_key_from_provider",
#     "webhook_ips": ["1.2.3.4", "5.6.7.8"],
#     "rate_limit": 100,
#     "signature_header": "X-Signature"
# }

# --- Email Configuration ---
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@runmycampus.com")
# Optional regional SMTP (Phase Welcome): map region_id to from_email; override in local_settings, e.g. REGIONAL_FROM_EMAIL = {"DEU": "noreply@eu.example.com"}
REGIONAL_FROM_EMAIL = {}

# v3.57.x Wave 8 Agent C — additive SMTP reliability + observability knobs.
# EMAIL_TIMEOUT: per-attempt socket timeout (seconds) for Django's SMTP
# backend. Lower = fail-fast on a dead server; higher = tolerate slow
# networks. apps.schoolops.email_delivery.get_resolved_smtp_config reads
# this as the fallback connection_timeout_seconds when no operator
# override is configured.
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
# EMAIL_USE_LOCALTIME: emit the Date: header in local time (with offset)
# rather than UTC. Operator-friendly for log correlation; MTAs accept either.
EMAIL_USE_LOCALTIME = True
# SCHOOLOPS_EMAIL_DELIVERY_RETRY_BACKOFF: per-attempt sleep (seconds)
# between SMTP send retries. Length of the list = total attempt count;
# the last entry is unused (no sleep after the final attempt). Tunable
# via a local_settings override; e.g. set [] to disable retries entirely.
SCHOOLOPS_EMAIL_DELIVERY_RETRY_BACKOFF = [1, 5, 30]
# v3.58.x Wave 9 Agent K — request-lifetime sync send budget.
# When the verification/transactional email path is invoked from inside an HTTP request,
# we cap the synchronous wall-clock budget at this many seconds regardless of how many
# retries the BACKOFF list configures. The signup view uses async_send=True to bypass
# this entirely.
SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS = int(os.getenv("SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS", "8"))
# v3.58.x Wave 9 Agent M — email reliability completion track.
# SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP: per-tenant sliding-window
# cap on transactional+bulk sends per hour. Default 200 — guards against
# runaway loops (signup spam, broken Celery beat, template regression).
# When send_transactional() is called WITHOUT a tenant_hash kwarg the
# cap is bypassed (platform-level sends like the operator test email).
SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP = int(os.getenv("SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP", "200"))
# SCHOOLOPS_EMAIL_DELIVERY_SSE_HEARTBEAT_SECONDS: cadence for the live
# email-health SSE stream at /super/email/health/stream/. Clamped to
# [1, 60] inside the view. 5s gives sub-perceptible live updates with
# negligible WSGI-worker load.
SCHOOLOPS_EMAIL_DELIVERY_SSE_HEARTBEAT_SECONDS = int(os.getenv("SCHOOLOPS_EMAIL_DELIVERY_SSE_HEARTBEAT_SECONDS", "5"))

# --- Caching Configuration ---
CACHES = {
    "default": {
        "BACKEND": os.getenv(
            "CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": os.getenv("CACHE_LOCATION", "unique-snowflake"),
        "TIMEOUT": 300,  # 5 minutes
    }
}

# Redis caching (if REDIS_URL is set)
REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    CACHES["default"] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
    }

# Optional: Redis-backed sessions when Redis is available (shared across workers)
if REDIS_URL and not RUNNING_TESTS:
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"
if RUNNING_TESTS:
    SESSION_ENGINE = "django.contrib.sessions.backends.db"

# --- Celery (background tasks; broker uses REDIS_URL when set) ---
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or REDIS_URL or ""
CELERY_RESULT_BACKEND = (
    "django-db"  # Store task results in Postgres; no Redis required for results
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = os.getenv("TIME_ZONE", "UTC")
CELERY_TASK_TRACK_STARTED = True
# Run tasks synchronously in test runs so no broker is required.
if RUNNING_TESTS:
    CELERY_TASK_ALWAYS_EAGER = True
# Optional: run celery beat with: celery -A config beat -l info
# Add periodic tasks in Django admin (django_celery_beat) or define CELERY_BEAT_SCHEDULE (see Celery docs).

# v3.32.0 — celery crontab schedule helper for entries that need a
# specific wall-clock time (e.g. Mondays 03:00 UTC for the legacy-hash
# sunset job). Imported lazily-guarded so a lightweight CI lane without
# Celery installed still imports settings.py cleanly.
try:
    from celery.schedules import crontab as _celery_crontab  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - celery is in requirements.txt
    _celery_crontab = None  # type: ignore[assignment]

# Celery Beat schedule for periodic tasks
# Optional tasks (requests reminder, deadline reminder) respect Site Settings: 0 = no-op
CELERY_BEAT_SCHEDULE = {
    # Move 2 — orchestration runner: drain pending runs every minute.
    "orchestration-process-due-runs": {
        "task": "orchestration.process_due_runs",
        "schedule": 60.0,
        "kwargs": {"limit": 50},
        "options": {"expires": 50},
    },
    # Move 2 — orchestration SLO aggregator: roll up the last hour every 5 minutes.
    "orchestration-aggregate-slos": {
        "task": "orchestration.aggregate_slos",
        "schedule": 300.0,
        "kwargs": {"window_minutes": 60},
        "options": {"expires": 240},
    },
    # Move 1 — marketplace webhook delivery: drain due webhook deliveries.
    "marketplace-webhook-deliver-due": {
        "task": "marketplace.webhook_deliver_due",
        "schedule": 30.0,
        "kwargs": {"limit": 50},
        "options": {"expires": 25},
    },
    # Move 4 — close help-center loop: evaluate AutoTicketRules every 10 minutes.
    "customersuccess-run-auto-ticket-rules": {
        "task": "customersuccess.run_auto_ticket_rules",
        "schedule": 600.0,
        "options": {"expires": 540},
    },
    "compliance-mark-sla-breaches": {
        "task": "compliance.mark_sla_breaches",
        "schedule": 3600.0,  # Hourly — GDPR Art. 12(3) one-month SLA, hourly granularity is fine
        "options": {"expires": 300},
    },
    # Glocal closeout — server-side offline queue replay (LCA / background_retry).
    "platform-runtime-process-offline-queues": {
        "task": "platform_runtime.process_offline_queues_due",
        "schedule": 300.0,
        "kwargs": {"limit_per_school": 25, "school_limit": 50},
        "options": {"expires": 240},
    },
    # v3.32.0 Agent 4 — daily sweep for low MealPlanBalance rows the
    # post_save signal missed (e.g. rows already low at app-startup).
    # Crontab 09:00 local CELERY_TIMEZONE when crontab is importable;
    # otherwise a 24-hour interval fallback. Task self-enforces a
    # 7-day cooldown per row, so an extra invocation is a safe no-op.
    "schoolops-sweep-low-meal-balances": {
        "task": "schoolops.sweep_low_meal_plan_balances",
        "schedule": (
            _celery_crontab(hour=9, minute=0)
            if _celery_crontab is not None else 86400.0
        ),
        "options": {"expires": 3600},
    },
    # Pass 13.E: nightly per-tenant policy/handbook RAG ingestion. No-op for
    # tenants that haven't set `school.settings["policy_doc_root"]`.
    "siteconfig-ingest-policy-documents": {
        "task": "siteconfig.ingest_policy_documents_all_tenants",
        "schedule": 86400.0,  # Daily
        "options": {"expires": 3600},
    },
    "send-payment-reminders": {
        "task": "finance.send_payment_reminders",
        "schedule": 3600.0,  # Every hour
        "options": {"expires": 300},  # Expire after 5 minutes if not picked up
    },
    "retry-failed-payment-reminders": {
        "task": "finance.retry_failed_payment_reminders",
        "schedule": 86400.0,  # Daily (24 hours)
        "options": {"expires": 3600},  # Expire after 1 hour
    },
    "retry-bank-verification": {
        "task": "finance.retry_bank_verification",
        "schedule": 86400.0,  # Daily (24 hours) - retry bank verification for pending receipts
        "options": {"expires": 3600},
        "kwargs": {"days_old": 30},  # Only retry receipts older than 30 days
    },
    "auto-generate-fee-invoices": {
        "task": "finance.auto_generate_fee_invoices",
        "schedule": 86400.0,  # Daily; task self-checks SiteSettings schedule mode
        "options": {"expires": 3600},
    },
    "auto-copy-fee-plans": {
        "task": "finance.auto_copy_fee_plans",
        "schedule": 86400.0,  # Daily; task self-checks SiteSettings mode/enable flags
        "options": {"expires": 3600},
    },
    "send-deadline-reminders": {
        "task": "analytics.send_deadline_reminders",
        "schedule": 86400.0,  # Daily; uses SiteSettings.teacher_deadline_reminder_days
        "options": {"expires": 600},
    },
    "remind-pending-access-request-assignees": {
        "task": "requests.remind_pending_assignees",
        "schedule": 86400.0,  # Daily; no-op when SiteSettings.requests_reminder_interval_hours == 0
        "options": {"expires": 600},
    },
    "expire-past-delegations": {
        "task": "accounts.expire_past_delegations",
        "schedule": 86400.0,  # Daily; respects SiteSettings.delegation_auto_revoke
        "options": {"expires": 600},
    },
    # v3.29 migration-cloud "password preservation moat" sunset job.
    # Find users with a foreign-vendor legacy_password_hash older than
    # 12 months who never completed first login; email a one-time setup
    # link; after the 30-day grace expires, null the legacy fields and
    # force a password reset. Weekly cadence is sufficient — the
    # operator runs the task with dry_run=True first on each cadence
    # via `python manage.py shell` to verify cohort size before
    # consenting to writes; production beat schedule below uses
    # dry_run=False so the cycle actually progresses.
    "accounts-sunset-stale-legacy-hashes": {
        "task": "accounts.sunset_stale_legacy_hashes",
        # v3.32.0 — upgraded to crontab form: Mondays 03:00 UTC. The
        # legacy-hash sunset job is non-urgent batch work; running it at
        # a predictable low-traffic wall-clock time makes the cohort
        # size easier for the on-call operator to spot-check. Falls
        # back to the previous 7-day interval when celery isn't
        # installed in the CI lane (kept identical cadence).
        "schedule": (
            _celery_crontab(hour=3, minute=0, day_of_week="mon")
            if _celery_crontab is not None
            else 604800.0
        ),
        "kwargs": {"dry_run": False, "age_months": 12, "grace_days": 30},
        "options": {"queue": "default", "expires": 3600},
    },
    # v3.33.0 Agent 4 — monthly orphan-ciphertext audit for the
    # MultiFernet rotation lifecycle. First of month, 04:00 UTC. The
    # task ONLY verifies (it does NOT auto-rotate) — if any orphans
    # are found, it emails the operator distribution list. Auto-rotate
    # is operator-driven via `python manage.py rotate_encryption_keys
    # --apply` so the operator is in the loop on every key migration.
    # Lazy-guarded for CI lanes without celery installed (falls back
    # to a ~30-day interval; the operator UTC alignment is best-effort
    # in that path).
    "accounts-key-rotation-monthly": {
        "task": "accounts.audit_encryption_key_orphans",
        "schedule": (
            _celery_crontab(hour=4, minute=0, day_of_month="1")
            if _celery_crontab is not None
            else 2592000.0
        ),
        "options": {"queue": "default", "expires": 3600},
    },
    # v3.39.0 Agent 1 — weekly Migration Cloud audit-chain verifier.
    # Mondays 02:00 UTC. Walks every active tenant's hash-chain via
    # ``manage.py verify_audit_chain --all-tenants`` and emails the
    # operator distribution list (``MIGRATION_CLOUD_AUDIT_OPS_EMAIL``)
    # ONLY when at least one chain is broken. The task NEVER raises
    # to the worker — verifier exceptions are logged at ERROR and
    # swallowed. Lazy-guarded so a CI lane without celery installed
    # still imports settings.py cleanly.
    "accounts-verify-audit-chain": {
        "task": "migration_cloud.verify_audit_chain_weekly",
        "schedule": (
            _celery_crontab(hour=2, minute=0, day_of_week="mon")
            if _celery_crontab is not None
            else 604800.0
        ),
        "options": {"queue": "default", "expires": 3600},
    },
    # v3.58.5 — daily capture of the 6 cockpit-pulse KPI cards so the dashboard
    # can render "+3 this week" deltas. Lightweight aggregate counts only —
    # no tenant slugs, no PII. Free 01:15 UTC slot per beat-schedule audit.
    "cockpit-platform-pulse-snapshot-daily": {
        "task": "siteconfig.snapshot_platform_pulse_daily",
        "schedule": (
            _celery_crontab(hour=1, minute=15)
            if _celery_crontab is not None
            else 86400.0
        ),
        "options": {"queue": "default", "expires": 3600},
    },
    # v3.34.0 Agent 5 — weekly upstream watch for django-cryptography
    # Django-5 compatibility. Mondays 05:00 UTC. The script ALWAYS exits
    # 0 (it's a watch, not a gate); the task layer parses the audit JSON
    # and emails the operator when a candidate release lands. NEVER
    # auto-upgrades — operator manually verifies + PRs the
    # requirements.txt bump per the docs/UPSTREAM_WATCH.md protocol.
    # Lazy-guarded behind CELERY_BEAT_ENABLED so dev / CI lanes can
    # disable upstream polling without code edits.
    **(
        {
            "upstream-watch-django-cryptography": {
                "task": "accounts.watch_django_cryptography_upstream",
                "schedule": (
                    _celery_crontab(hour=5, minute=0, day_of_week=1)
                    if _celery_crontab is not None
                    else 604800.0
                ),
                "options": {"queue": "default", "expires": 3600},
            },
            # Help-center tier batch 1341 — KB freshness + code index weekly.
            "portal-reindex-kb-embeddings-weekly": {
                "task": "portal.reindex_kb_help_embeddings_weekly",
                "schedule": (
                    _celery_crontab(hour=3, minute=30, day_of_week=0)
                    if _celery_crontab is not None
                    else 604800.0
                ),
                "options": {"expires": 7200},
            },
            "portal-build-code-support-index-weekly": {
                "task": "portal.build_code_support_index_weekly",
                "schedule": (
                    _celery_crontab(hour=4, minute=0, day_of_week=0)
                    if _celery_crontab is not None
                    else 604800.0
                ),
                "options": {"expires": 7200},
            },
            "portal-purge-help-telemetry-monthly": {
                "task": "portal.purge_help_telemetry_monthly",
                "schedule": (
                    _celery_crontab(hour=5, minute=0, day_of_month=1)
                    if _celery_crontab is not None
                    else 2592000.0
                ),
                "options": {"expires": 7200},
            },
            "portal-help-north-star-weekly-email": {
                "task": "portal.help_north_star_weekly_email",
                "schedule": (
                    _celery_crontab(hour=6, minute=0, day_of_week=1)
                    if _celery_crontab is not None
                    else 604800.0
                ),
                "options": {"expires": 7200},
            },
            "portal-archive-stale-kb-articles-monthly": {
                "task": "portal.archive_stale_kb_articles_monthly",
                "schedule": (
                    _celery_crontab(hour=6, minute=30, day_of_month=1)
                    if _celery_crontab is not None
                    else 2592000.0
                ),
                "options": {"expires": 7200},
            },
        }
        if CELERY_BEAT_ENABLED
        else {}
    ),
    "update-invoice-statuses": {
        "task": "finance.update_invoice_statuses",
        "schedule": 86400.0,  # Daily
        "options": {"expires": 600},
    },
    "calculate-monthly-revenue-stats": {
        "task": "siteconfig.calculate_monthly_revenue_stats",
        "schedule": 86400.0,  # Daily (Phase E: RevenueSnapshot, waiver metrics)
        "options": {"expires": 3600},
    },
    "nightly-risk-factors": {
        "task": "analytics.nightly_risk_factors",
        "schedule": 86400.0,  # Daily; computes RiskFactor per school for at-risk dashboard
        "options": {"expires": 3600},
    },
    "kudos-perfect-attendance-3d": {
        "task": "communication.kudos_perfect_attendance_3d",
        "schedule": 86400.0,  # Daily; Plan XIII: 3 days perfect attendance → AchievementEvent + AI narrative
        "options": {"expires": 600},
    },
    "check-badge-expiry-alerts": {
        "task": "people.check_badge_expiry_alerts",
        "schedule": 86400.0,  # Daily; Plan XI: certification/badge expiry notifications (e.g. 60 days)
        "options": {"expires": 600},
        "kwargs": {"days": 60},
    },
    "marketplace-health-check": {
        "task": "marketplace.marketplace_health_check",
        "schedule": 21600.0,  # Every 6 hours
        "options": {"expires": 600},
    },
    # Event outbox and notification queue (required for internal-first)
    "process-event-outbox": {
        "task": "apps.events.process_event_outbox",
        "schedule": 120.0,  # Every 2 minutes
        "options": {"expires": 300},
        "kwargs": {"batch_size": 100},
    },
    "process-outbound-message-queue": {
        "task": "communication.process_outbound_message_queue",
        "schedule": 120.0,  # Every 2 minutes
        "options": {"expires": 300},
        "kwargs": {"limit": 50},
    },
    # §0.1.5 Wave 5: scheduled migration exception / quarantine telemetry
    "migration-scheduled-parity-tick": {
        "task": "automation.migration_scheduled_parity_tick",
        "schedule": 86400.0,
        "options": {"expires": 3600},
    },
    # v2.79: refresh per-tenant OAuth tokens before they expire. Without this,
    # every connected integration breaks ~1h after first connect.
    # Cadence chosen to fit inside the 10-min `_is_due()` window with margin.
    "integrations-refresh-oauth-tokens": {
        "task": "integrations_marketplace.refresh_due_oauth_tokens",
        "schedule": 300.0,  # Every 5 minutes
        "options": {"expires": 240},
    },
    # v2.100: renew calendar/mail push subscriptions before they expire.
    # Google Calendar channels last ~30d, Graph subscriptions ~3d — without
    # this, push delivery silently stops and tenants get no notifications.
    "integrations-renew-push-subscriptions": {
        "task": "integrations_marketplace.renew_due_subscriptions",
        "schedule": 3600.0,  # Hourly is plenty given the 1-day renewal window.
        "options": {"expires": 3300},
    },
    # v2.100: fetch new messages for OAuth-connected mailboxes (gmail / outlook_mail).
    # Inbound-mail tenants depend on this to see anything land in their app.
    "integrations-fetch-mailboxes": {
        "task": "integrations_marketplace.fetch_due_mailboxes",
        "schedule": 300.0,  # Every 5 minutes — tunable per provider quota.
        "options": {"expires": 240},
    },
    # v3.32.0 — Migration Cloud REST API webhook dispatcher. Drains due
    # MigrationCloudWebhookDelivery rows (status=pending,
    # next_retry_at <= now) every 30s. Per-tenant hourly quota enforced
    # in the task body (1000/hr default); over-quota rows are deferred
    # to the next hour boundary instead of attempted.
    "migration-cloud-webhook-deliver-due": {
        "task": "apps.migration_cloud.api.webhook_dispatch.deliver_due_task",
        "schedule": 30.0,  # seconds
        "options": {"queue": "default", "expires": 60},
    },
    # v3.40.0 Agent 8 — nightly Migration Cloud end-to-end smoke against
    # the synthetic tenant. 04:30 UTC daily. Dry-run ONLY (the task body
    # never passes --apply) so a leaking dev kill-switch can't perturb
    # prod state. Kill-switched via
    # ``MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED`` (default False); the
    # task short-circuits before invoking the command when the switch
    # is off. Emits a ``migration.smoke.nightly_run`` audit event on
    # every run; emails ``MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL`` only
    # on failure (one mail per run; no per-section spam).
    "migration-cloud-smoke-nightly": {
        "task": (
            "apps.migration_cloud.tasks_smoke."
            "run_smoke_against_synthetic_tenant"
        ),
        "schedule": (
            _celery_crontab(hour=4, minute=30)
            if _celery_crontab is not None
            else 86400.0
        ),
        "options": {"queue": "low_priority", "expires": 3600},
    },
    # v3.40.0 Agent 12 — operator alert source: token rotation watchdog.
    # Daily 03:30 UTC scan for API tokens whose ``grace_until`` has
    # elapsed and which have no successor; emits one warning per overdue
    # token (rate-limited by ``apps.migration_cloud.alerts``).
    "migration-cloud-token-rotation-watchdog": {
        "task": "apps.migration_cloud.tasks_alerts.token_rotation_watchdog",
        "schedule": (
            _celery_crontab(hour=3, minute=30)
            if _celery_crontab is not None
            else 86400.0
        ),
        "options": {"queue": "low_priority", "expires": 3600},
    },
    # v3.40.0 Agent 15 — monthly retention audit (DRY-RUN). First-of-month
    # 05:00 UTC; sweeps every tenant and counts purge-eligible ciphertext
    # blobs older than MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS. Emits one
    # ``severity="info"`` alert per tenant with non-zero candidates so
    # the operator can schedule the actual ``--apply`` invocation behind
    # counsel signoff. NEVER mutates.
    "migration-cloud-retention-audit-monthly": {
        "task": (
            "apps.migration_cloud.tasks_retention."
            "purge_completed_migration_bundles_audit_task"
        ),
        "schedule": (
            _celery_crontab(day_of_month=1, hour=5, minute=0)
            if _celery_crontab is not None
            else 2592000.0  # ~30 days fallback when crontab unavailable
        ),
        "options": {"queue": "low_priority", "expires": 3600},
    },
}
# Public demo refresh: set ENSURE_DEMO_CRON_SLUG (e.g. demo-school) and run Celery beat.
_ensure_demo_cron_slug = (os.getenv("ENSURE_DEMO_CRON_SLUG") or "").strip()
if _ensure_demo_cron_slug:
    CELERY_BEAT_SCHEDULE["ensure-demo-environment-daily"] = {
        "task": "schools.ensure_demo_environment_scheduled",
        "schedule": 86400.0,
        "options": {"expires": 7200},
    }

if os.getenv("TENANT_AUTO_PURGE_ENABLED", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["schools-run-scheduled-tenant-purges"] = {
        "task": "schools.run_scheduled_tenant_purges",
        "schedule": (
            _celery_crontab(hour=4, minute=15)
            if _celery_crontab is not None
            else 86400.0
        ),
        "kwargs": {"dry_run": False, "limit": 20},
        "options": {"queue": "low_priority", "expires": 3600},
    }

# Backlog unlock matrix: refresh Django cache + emit PlatformEventLog on dependency transitions.
# Opt-in — runs multiple repo gate scripts (CPU + minutes). See docs/BACKLOG_UNLOCK_AUTOMATION.md.
if os.getenv("ENABLE_BACKLOG_UNLOCK_BEAT", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["backlog-unlock-evaluate-cache"] = {
        "task": "platform_runtime.backlog_unlock_eval_and_cache",
        "schedule": 86400.0,
        "options": {"expires": 3600},
    }

# Open-source AI ops: refresh local Ollama weights on a schedule (requires Ollama on worker host).
if os.getenv("ENABLE_OLLAMA_MODEL_SYNC_BEAT", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["ollama-model-sync-weekly"] = {
        "task": "platform_runtime.sync_ollama_models_beat",
        "schedule": 604800.0,
        "options": {"expires": 7200},
    }

# RAG: refresh AI embedding index (requires working embedding provider on worker host).
if os.getenv("ENABLE_AI_KNOWLEDGE_INDEX_BEAT", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["index-ai-knowledge-daily"] = {
        "task": "siteconfig.index_ai_knowledge_beat",
        "schedule": 86400.0,
        "options": {"expires": 3600},
    }

# Platform health: operator-visible Celery+DB ticks (non-migration).
if os.getenv("ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT", "").strip().lower() in (
    "1",
    "true",
    "yes",
):
    CELERY_BEAT_SCHEDULE["operator-visibility-heartbeat-daily"] = {
        "task": "platform_runtime.operator_visibility_heartbeat",
        "schedule": 86400.0,
        "options": {"expires": 600},
    }
if os.getenv("ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT", "").strip().lower() in (
    "1",
    "true",
    "yes",
):
    CELERY_BEAT_SCHEDULE["database-connectivity-heartbeat-daily"] = {
        "task": "platform_runtime.database_connectivity_heartbeat",
        "schedule": 86400.0,
        "options": {"expires": 300},
    }
if os.getenv("ENABLE_AUTOMATION_FAILURE_TREND_BEAT", "").strip().lower() in (
    "1",
    "true",
    "yes",
):
    CELERY_BEAT_SCHEDULE["automation-failure-trend-daily"] = {
        "task": "platform_runtime.automation_failure_trend_signal",
        "schedule": 86400.0,
        "options": {"expires": 600},
    }
if os.getenv("ENABLE_AI_QUALITY_SCORECARD_BEAT", "").strip().lower() in (
    "1",
    "true",
    "yes",
):
    CELERY_BEAT_SCHEDULE["ai-quality-scorecard-weekly"] = {
        "task": "siteconfig.ai_quality_scorecard_beat",
        "schedule": 604800.0,
        "options": {"expires": 3600},
    }

# AI/ML predictive batches (Waves 1-10). Each opt-in via env var so a
# fresh deploy doesn't start scoring before operators have an artifact.
if os.getenv("ENABLE_AT_RISK_NIGHTLY_BEAT", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["analytics-compute-nightly-risk"] = {
        "task": "analytics.compute_nightly_risk",
        "schedule": 86400.0,
        "options": {"expires": 7200},
    }
if os.getenv("ENABLE_GRADE_PREDICTION_NIGHTLY_BEAT", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["analytics-compute-nightly-grade-predictions"] = {
        "task": "analytics.compute_nightly_grade_predictions",
        "schedule": 86400.0,
        "options": {"expires": 7200},
    }
if os.getenv("ENABLE_STUDENT_EMBEDDINGS_BEAT", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["analytics-build-student-embeddings"] = {
        "task": "analytics.build_student_embeddings",
        "schedule": 86400.0,
        "options": {"expires": 7200},
    }
if os.getenv("ENABLE_RISK_DIGEST_BEAT", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["analytics-send-risk-digest-daily"] = {
        "task": "analytics.send_risk_digest_all",
        "schedule": 86400.0,
        "options": {"expires": 3600},
    }
if os.getenv("ENABLE_AT_RISK_DRIFT_WATCHDOG_BEAT", "").strip().lower() in ("1", "true", "yes"):
    CELERY_BEAT_SCHEDULE["analytics-at-risk-drift-watchdog"] = {
        "task": "analytics.check_at_risk_drift_watchdog",
        "schedule": 86400.0,
        "options": {"expires": 3600},
    }

# --- Logging Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Create logs directory if it doesn't exist (for file logging)
LOG_DIR = BASE_DIR / "logs"
USE_FILE_LOGGING = os.getenv("USE_FILE_LOGGING", str(DEBUG)) == "True"
# Disable file logging during test runs to avoid RotatingFileHandler lock/rename issues (e.g. Windows)
if RUNNING_TESTS:
    USE_FILE_LOGGING = False

# Only create logs directory if file logging is enabled
if USE_FILE_LOGGING:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except (OSError, PermissionError):
        # If we can't create the directory, disable file logging
        USE_FILE_LOGGING = False

# Build handlers list (request_context filter adds request_id, tenant_id, user_id, school_id — A4)
LOGGING_HANDLERS = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "json" if os.getenv("LOG_JSON", "0") == "1" else "verbose_request",
        "level": LOG_LEVEL,
        "filters": ["request_context"],
    },
}

# Optional per-file size cap (MB). Default 10; set LOG_FILE_MAX_MB=5 to reduce.
LOG_FILE_MAX_MB = int(os.getenv("LOG_FILE_MAX_MB", "10"))
if LOG_FILE_MAX_MB < 1:
    LOG_FILE_MAX_MB = 10

# Add file handler only if file logging is enabled and directory exists
if USE_FILE_LOGGING:
    LOGGING_HANDLERS["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": LOG_DIR / "django.log",
        "maxBytes": 1024 * 1024 * LOG_FILE_MAX_MB,
        "backupCount": 10,
        "formatter": "json" if os.getenv("LOG_JSON", "0") == "1" else "verbose_request",
        "level": LOG_LEVEL,
        "filters": ["request_context"],
    }

# Determine which handlers to use
ACTIVE_HANDLERS = ["console", "file"] if USE_FILE_LOGGING else ["console"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "apps.observability.logging_context.RequestContextFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "verbose_request": {
            "format": (
                "%(levelname)s %(asctime)s request_id=%(request_id)s tenant_id=%(tenant_id)s "
                "user_id=%(user_id)s school_id=%(school_id)s http_method=%(http_method)s "
                "request_path=%(request_path)s remote_addr=%(remote_addr)s "
                "http_referer=%(http_referer)s http_user_agent=%(http_user_agent)s "
                "http_host=%(http_host)s content_type=%(content_type)s "
                "accept_language=%(accept_language)s accept_encoding=%(accept_encoding)s "
                "x_forwarded_for=%(x_forwarded_for)s x_forwarded_proto=%(x_forwarded_proto)s "
                "x_forwarded_host=%(x_forwarded_host)s "
                "content_length=%(content_length)s "
                "http_origin=%(http_origin)s "
                "query_string=%(query_string)s "
                "server_protocol=%(server_protocol)s "
                "request_scheme=%(request_scheme)s "
                "server_name=%(server_name)s "
                "%(message)s"
            ),
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": (
                "%(levelname)s %(asctime)s %(name)s %(module)s %(process)d %(thread)d "
                "request_id=%(request_id)s tenant_id=%(tenant_id)s user_id=%(user_id)s "
                "school_id=%(school_id)s http_method=%(http_method)s "
                "request_path=%(request_path)s remote_addr=%(remote_addr)s "
                "http_referer=%(http_referer)s http_user_agent=%(http_user_agent)s "
                "http_host=%(http_host)s content_type=%(content_type)s "
                "accept_language=%(accept_language)s accept_encoding=%(accept_encoding)s "
                "x_forwarded_for=%(x_forwarded_for)s x_forwarded_proto=%(x_forwarded_proto)s "
                "x_forwarded_host=%(x_forwarded_host)s "
                "content_length=%(content_length)s "
                "http_origin=%(http_origin)s "
                "query_string=%(query_string)s "
                "server_protocol=%(server_protocol)s "
                "request_scheme=%(request_scheme)s "
                "server_name=%(server_name)s "
                "%(message)s"
            ),
        },
    },
    "handlers": LOGGING_HANDLERS,
    "root": {
        "handlers": ACTIVE_HANDLERS,
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.request": {
            "handlers": ACTIVE_HANDLERS,
            "level": "ERROR",
            "propagate": False,
        },
        "django.db": {
            "handlers": ["console"],
            "level": "WARNING" if RUNNING_TESTS else ("DEBUG" if DEBUG else "WARNING"),
            "propagate": False,
        },
    },
}

# --- Compliance Alerts & Reporting ---
COMPLIANCE_ALERTS = {
    # Enable/disable alert dispatching globally
    "enabled": os.getenv("COMPLIANCE_ALERTS_ENABLED", "1") == "1",
    # Sensitivity threshold for real-time alerts (LOW, MEDIUM, HIGH, CRITICAL)
    "severity_threshold": os.getenv("COMPLIANCE_ALERTS_THRESHOLD", "HIGH"),
    # Actions that should always alert regardless of sensitivity
    "escalate_on_actions": os.getenv(
        "COMPLIANCE_ALERT_ACTIONS",
        "ACCESS_DENIED,DELETE,PERM_GRANT,PERM_REVOKE,APPROVE,REJECT",
    ).split(","),
    # Channels
    "email_recipients": [
        e for e in os.getenv("COMPLIANCE_ALERT_EMAILS", "").split(",") if e
    ],
    "slack_webhook_url": os.getenv("COMPLIANCE_ALERT_SLACK_WEBHOOK", ""),
    "generic_webhook_url": os.getenv("COMPLIANCE_ALERT_WEBHOOK", ""),
    # Runbook / on-call guidance
    "runbook_url": os.getenv(
        "COMPLIANCE_RUNBOOK_URL",
        "https://runbooks.runmycampus.com/security/incident-response",
    ),
    # Scheduled compliance report recipients
    "report_recipients": [
        e for e in os.getenv("COMPLIANCE_REPORT_RECIPIENTS", "").split(",") if e
    ],
    "report_email_enabled": os.getenv("COMPLIANCE_REPORT_EMAIL_ENABLED", "1") == "1",
}

# --- DRF + OpenAPI (drf-spectacular) ---
# Public API surface auto-documented at /api/schema/ (raw OpenAPI 3.0 JSON/YAML),
# /api/docs/ (Swagger UI), and /api/redoc/ (Redoc).
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Authentication classes default to session + simplejwt; keep ordering so
    # browser sessions still work and API clients can use Bearer tokens.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    # Pass 12: cursor pagination is opaque (clients can't skip pages or guess IDs)
    # and stable under inserts — better default for our high-write tenant tables.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.CursorPagination",
    "PAGE_SIZE": int(os.getenv("API_DEFAULT_PAGE_SIZE", "50")),
    # Pass 12: RFC 7807 problem+json envelope on every error response.
    "EXCEPTION_HANDLER": "apps.api.exception_handler.rfc7807_exception_handler",
    # v3.33.0: Migration Cloud global throttle. Path-scoped — short-circuits
    # to NO-OP for any request whose path does not contain
    # ``/migration/api/v1/``, so non-Migration-Cloud DRF surfaces keep
    # their existing semantics. Three internal scopes:
    #   * webhook_tenant  — 1000/hour (any /webhooks/ path)
    #   * bundles_write   — 600/min   (unsafe HTTP method)
    #   * bundles_read    — 100/min   (safe HTTP method)
    # See ``apps/migration_cloud/api/rate_limiting.py``.
    "DEFAULT_THROTTLE_CLASSES": (
        "apps.migration_cloud.api.rate_limiting.MigrationCloudGlobalThrottle",
    ),
}

# --- JWT (rest_framework_simplejwt) ---
from datetime import timedelta as _jwt_timedelta

_jwt_access_minutes = int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "60"))
_jwt_refresh_days = int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": _jwt_timedelta(minutes=max(5, _jwt_access_minutes)),
    "REFRESH_TOKEN_LIFETIME": _jwt_timedelta(days=max(1, _jwt_refresh_days)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# v3.33.0: SSE deployment transport mode. ``wsgi-fallback`` emits a
# one-shot snapshot frame and closes (safe under sync Gunicorn workers);
# ``asgi-daphne`` runs the full 60s long-poll loop. See
# ``docs/SSE_DAPHNE_DEPLOYMENT.md`` for the operator runbook.
MIGRATION_CLOUD_SSE_TRANSPORT = os.getenv(
    "MIGRATION_CLOUD_SSE_TRANSPORT", "wsgi-fallback",
).strip().lower()

# v3.35.0 — Webhook header family migration window.
#
# The outbound webhook dispatcher emits BOTH the new canonical
# ``X-RunMyCampus-*`` header family AND the legacy ``X-Migration-Cloud-*``
# header family during a 90-day deprecation window so existing customer
# verifier code continues to work. After 2026-08-18 the legacy family
# will be removed in v3.40.0 (or the earliest release on/after that
# date). Customers should migrate their verifier code to the new family
# during the window — see ``docs/WEBHOOK_HEADER_MIGRATION_2026.md``.
#
# Default ON for backwards-compat. Operators flip
# ``RMC_EMIT_LEGACY_WEBHOOK_HEADERS=0`` once all their downstream
# receivers have migrated.
MIGRATION_CLOUD_EMIT_LEGACY_HEADERS = (
    os.environ.get("RMC_EMIT_LEGACY_WEBHOOK_HEADERS", "1").strip() == "1"
)
MIGRATION_CLOUD_LEGACY_HEADER_DEPRECATION_DATE = "2026-08-18"

# v3.39.0 Agent 1 — Migration Cloud audit-chain verifier ops email.
# The weekly Celery beat ``accounts-verify-audit-chain`` (Mondays 02:00
# UTC) invokes ``manage.py verify_audit_chain --all-tenants`` and only
# emails this address when at least one tenant chain is BROKEN. The
# body NEVER carries raw hash bytes, payload bytes, or tenant slugs —
# only tenant_id_hash prefixes, counts, and first-broken-event UUIDs.
# Empty string disables the email arm (the beat still runs the
# verifier and logs); operators set the env var per environment.
MIGRATION_CLOUD_AUDIT_OPS_EMAIL = (
    os.environ.get("MIGRATION_CLOUD_AUDIT_OPS_EMAIL", "") or ""
).strip()

# v3.39.0 Agent 1 — Counsel-pending audit retention purge approval
# token. The ``purge_audit_events_pre_approved`` management command
# REFUSES to run without ``--counsel-approval-token=<value>`` matching
# this setting via constant-time compare. Empty string (default) makes
# the command print a counsel-pending message and exit 1 regardless of
# the supplied flag — the operator MUST provision the env var only
# AFTER the counsel signoff PDF is on file (see
# docs/MIGRATION_CLOUD_AUDIT_LOG.md § Retention purge procedure).
MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN = (
    os.environ.get("MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN", "") or ""
).strip()

# v3.39.0 Agent 2 — Migration Cloud audit-event root-key signature.
#
# When ``MIGRATION_CLOUD_AUDIT_SIGNING_KEY`` is set (base64 over >= 32
# random bytes recommended), every new audit event is signed with
# HMAC-SHA512 over the SAME canonical-JSON pre-image that
# ``integrity_hash`` covers. The hex digest is stored on the event's
# ``root_key_signature`` field and re-verified by:
#
#   * ``python manage.py verify_audit_chain --check-root-signature``
#   * the JSONL export view when ``?verify_root_signature=1`` is set
#
# Defends against the "restore-from-tampered-backup" attack: even if
# every byte of the audit table is altered, an attacker who lacks the
# signing key cannot regenerate a matching signature. SHA-512 is used
# (rather than SHA-256, which ``integrity_hash`` already uses) so a
# single-key compromise cannot collapse both checks at once.
#
# Operational guidance — see docs/SECURITY_KEYS.md "Audit-event root-key
# signature" section. NEVER commit a literal key value here; read from
# the environment only.
#
# ``MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND`` selects the signing surface:
#   * ``local-env-key`` — default; HMAC with the env-loaded key.
#   * ``aws-kms`` / ``azure-keyvault`` / ``hashicorp-vault`` / ``gcp-kms``
#     — reserved; current implementation raises NotImplementedError
#     with "configure HSM bridge first" message + docs reference.
MIGRATION_CLOUD_AUDIT_SIGNING_KEY = os.environ.get(
    "MIGRATION_CLOUD_AUDIT_SIGNING_KEY", ""
)
MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND = os.environ.get(
    "MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND", "local-env-key"
)

# v3.40.0 Agent 1 — HashiCorp Vault Transit backend dry-run flag.
#
# When ``MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND=hashicorp-vault`` and this
# flag is "1" (the dev default), the vault backend returns deterministic
# 128-char base64 placeholders instead of calling Vault. Production
# deployments MUST set this to "0" and provision real Vault transit
# access. See docs/MIGRATION_CLOUD_HSM_VAULT.md for the operator
# playbook (VAULT_ADDR, VAULT_TOKEN, MIGRATION_CLOUD_VAULT_TRANSIT_KEY_NAME,
# MIGRATION_CLOUD_VAULT_NAMESPACE for Enterprise).
MIGRATION_CLOUD_VAULT_DRY_RUN = os.environ.get(
    "MIGRATION_CLOUD_VAULT_DRY_RUN", "1"
) == "1"

# v3.40.0 Agent 8 — Migration Cloud nightly smoke task config.
#
# ``MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED`` is the kill-switch for the
# beat-scheduled nightly invocation of ``manage.py migration_cloud_smoke``
# against the synthetic tenant. Default OFF so prod is never perturbed;
# operators flip to "1" in dev / staging environments.
#
# ``MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT`` is the slug of the synthetic
# tenant the nightly run targets (the same slug operators pass to the
# manual ``--tenant=`` invocation; default ``smoke-test-tenant``).
#
# ``MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL`` receives one email per
# non-clean nightly run (exit_code != 0 OR any section failed). PII-free
# body — counts and exit code only. Empty string = no email.
MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED = (
    os.environ.get("MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED", "0").strip() == "1"
)
MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT = (
    os.environ.get(
        "MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT", "smoke-test-tenant"
    ) or "smoke-test-tenant"
).strip()
MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL = (
    os.environ.get("MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL", "") or ""
).strip() or None

# v3.40.0 Agent 14 — Per-tenant audit-event volume rate-limit.
#
# Guards the append-only audit chain against runaway emit loops (bad
# call site, malicious caller). The limit applies per
# (tenant_id_hash, event_type) pair on a sliding 1h window. Sliding
# state is in-memory only — worker restart resets the counter
# (acceptable because the guard is a runaway-mitigation, NOT a
# hard cap; see docs/MIGRATION_CLOUD_AUDIT_RATE_LIMITING.md).
#
#   MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR
#     Default 5000. Recommended floor 100 — anything lower risks
#     refusing legitimate edge bursts (mass guardian-consent campaigns,
#     domain-wide MAA re-sign flows).
#
#   MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED
#     Emergency kill-switch. Set to "1" when a legitimate burst is
#     happening (e.g., mass MAA signature drive) and the operator
#     wants the chain to absorb it un-rate-limited. Default OFF.
MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR = int(
    os.environ.get(
        "MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR", "5000"
    ) or "5000"
)
MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED = (
    os.environ.get(
        "MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED", "0"
    ).strip() == "1"
)

# v3.40.0 Agent 12 — operator alert routing (Slack + PagerDuty + email).
#
# ``OPERATOR_ALERT_EMAIL`` is the v3.40 alias for the v3.39 setting; the
# alerts module checks both. Empty = email channel disabled.
#
# ``OPERATOR_ALERT_SLACK_WEBHOOK_URL`` — Incoming Webhook URL for the
# operator on-call Slack channel. Empty = Slack channel disabled. The
# alerts module sha256-prefixes this URL before any log emission, so
# the raw URL never lands in log aggregators.
#
# ``OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY`` — Events API v2 routing
# key for the Migration Cloud service. Empty = PagerDuty channel
# disabled. Critical-severity alerts page; warnings do NOT.
#
# ``OPERATOR_ALERT_DRY_RUN`` defaults to "1" (ON). Channels log the
# would-send payload but do NOT POST. Flip to "0" in production
# deliberately — the alerts module reads the value lazily so an
# operator can toggle without a redeploy.
#
# ``OPERATOR_ALERT_RATE_LIMIT_PER_HOUR`` caps distinct dedup_keys per
# rolling hour to prevent a stale-state stampede (e.g. 200 overdue
# tokens at once). Default 50.
#
# See ``docs/MIGRATION_CLOUD_OPERATOR_ALERTS.md`` for the full severity
# routing table + incident response decision tree.
OPERATOR_ALERT_EMAIL = (
    os.environ.get("OPERATOR_ALERT_EMAIL", "") or ""
).strip() or MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL
# Help north-star weekly digest (batch 1356); falls back to OPERATOR_ALERT_EMAIL.
HELP_NORTH_STAR_WEEKLY_EMAIL = (
    os.environ.get("HELP_NORTH_STAR_WEEKLY_EMAIL", "") or ""
).strip() or OPERATOR_ALERT_EMAIL
OPERATOR_ALERT_SLACK_WEBHOOK_URL = (
    os.environ.get("OPERATOR_ALERT_SLACK_WEBHOOK_URL", "") or ""
).strip() or None
OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY = (
    os.environ.get("OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY", "") or ""
).strip() or None
OPERATOR_ALERT_DRY_RUN = (
    os.environ.get("OPERATOR_ALERT_DRY_RUN", "1") or "1"
).strip() not in ("0", "false", "False", "")
try:
    OPERATOR_ALERT_RATE_LIMIT_PER_HOUR = max(
        1, int(os.environ.get("OPERATOR_ALERT_RATE_LIMIT_PER_HOUR", "50"))
    )
except (TypeError, ValueError):
    OPERATOR_ALERT_RATE_LIMIT_PER_HOUR = 50

# v3.40.0 Agent 15 — Migration data retention purge config (FERPA §99.30).
#
# Counterpart to ``MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN`` — gates
# the ``purge_completed_migration_bundles`` management command. Empty
# string (default) makes the command print a counsel-pending message
# on --apply and exit 1.
#
#   MIGRATION_CLOUD_RETENTION_MIN_DAYS
#     Hard floor on --older-than-days. The command refuses N < this.
#     Default 90 (FERPA + counsel-blessed minimum).
#
#   MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS
#     Default cadence the monthly audit task uses when sweeping
#     tenants. Default 180.
#
#   MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN
#     Token compared with ``hmac.compare_digest`` when --apply is set.
#     NEVER commit a literal value here; read from the environment.
#
# See ``docs/MIGRATION_CLOUD_DATA_RETENTION.md`` for the operator
# playbook.
try:
    MIGRATION_CLOUD_RETENTION_MIN_DAYS = max(
        1, int(os.environ.get("MIGRATION_CLOUD_RETENTION_MIN_DAYS", "90"))
    )
except (TypeError, ValueError):
    MIGRATION_CLOUD_RETENTION_MIN_DAYS = 90
try:
    MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS = max(
        MIGRATION_CLOUD_RETENTION_MIN_DAYS,
        int(os.environ.get("MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS", "180")),
    )
except (TypeError, ValueError):
    MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS = 180
MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN = (
    os.environ.get("MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN", "") or ""
).strip()

# v3.40.0 Agent 15 — Throttle-bucket saturation alert hook.
#
# When any rate-limit bucket exceeds ratio R in a 1m window the
# ``TenantRateLimiter._check_saturation_alert`` hook emits a
# ``severity="warning"`` alert (Agent 12's surface). Bucket name is
# sha256-prefixed in the alert title; no raw bucket keys land in the
# log aggregator.
#
#   MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_RATIO
#     Ratio threshold (default 0.95). Floats accepted.
#
#   MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_DISABLED
#     Emergency kill switch. Set to "1" to suppress all saturation
#     alerts. Default OFF.
try:
    MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_RATIO = float(
        os.environ.get(
            "MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_RATIO", "0.95"
        ) or "0.95"
    )
except (TypeError, ValueError):
    MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_RATIO = 0.95
MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_DISABLED = (
    os.environ.get(
        "MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_DISABLED", "0"
    ).strip() == "1"
)

# Pass 12: CORS allowlist. Strict by default; SiteConfig can extend per tenant
# at request time via a middleware (django-cors-headers honors the dynamic list
# through CORS_ALLOWED_ORIGINS_REGEXES at startup).
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
# Never allow wildcard CORS in production — explicit origins + tenant subdomain regex only.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "0") == "1"
CORS_ALLOWED_ORIGIN_REGEXES = []
if _multi_tenant_base:
    CORS_ALLOWED_ORIGIN_REGEXES.append(
        rf"^https://[a-z0-9-]+\.{re.escape(_multi_tenant_base)}$"
    )
for _legacy_base in _legacy_bases:
    CORS_ALLOWED_ORIGIN_REGEXES.append(
        rf"^https://[a-z0-9-]+\.{re.escape(_legacy_base)}$"
    )

SPECTACULAR_SETTINGS = {
    "TITLE": "RunMyCampus API",
    "DESCRIPTION": (
        "Public REST API for RunMyCampus. Multi-tenant school management SaaS. "
        "Each endpoint is tenant-scoped — your API key / session determines which "
        "school's data you can read or write."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,  # Don't include the /schema route itself in the schema
    "CONTACT": {"email": "developers@runmycampus.com"},
    "LICENSE": {"name": "Proprietary"},
    "SERVERS": [
        {"url": "https://api.runmycampus.com", "description": "Production"},
        {"url": "https://api.staging.runmycampus.com", "description": "Staging"},
    ],
    "TAGS": [
        {"name": "Students"},
        {"name": "Teachers"},
        {"name": "Guardians"},
        {"name": "Attendance"},
        {"name": "Grades"},
        {"name": "Finance"},
        {"name": "Reports"},
        {"name": "Webhooks"},
        # Pass 14: marketplace public catalog (apps + scopes).
        {"name": "Marketplace"},
    ],
    # Group endpoints by URL prefix for navigability.
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
    # Hide internal/non-stable endpoints from the public docs by excluding them with
    # the `extend_schema(exclude=True)` decorator on the view.
}

# --- Observability metrics bridge (v3.39.0 Agent 4) ---
# Pluggable backend dispatch for platform metric emission. Default is
# "noop" so dev / test never emit. Production sets one of:
#   "structured-log"    — JSON line on logging.getLogger("observability.metrics")
#   "prometheus-client" — wraps prometheus_client (optional dep)
#   "statsd"            — wraps statsd (optional dep)
# If the requested backend's library is not installed, the bridge falls
# back to "structured-log" and logs a one-time WARNING. See
# apps/observability/metrics.py and docs/OBSERVABILITY_METRICS.md.
OBSERVABILITY_METRICS_BACKEND = os.getenv("OBSERVABILITY_METRICS_BACKEND", "noop")
OBSERVABILITY_METRICS_STATSD_HOST = os.getenv("OBSERVABILITY_METRICS_STATSD_HOST", "")
OBSERVABILITY_METRICS_STATSD_PORT = int(
    os.getenv("OBSERVABILITY_METRICS_STATSD_PORT", "8125")
)
OBSERVABILITY_PROMETHEUS_NAMESPACE = os.getenv(
    "OBSERVABILITY_PROMETHEUS_NAMESPACE", "runmycampus"
)

# --- Sentry (error and performance monitoring) ---
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05"))
SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0"))

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    # Pass 11: CeleryIntegration is critical — without it, every error inside a
    # background task is invisible to Sentry. Imported lazily so non-Celery
    # deployments (e.g. tests, ad-hoc scripts) don't pay the import cost.
    _sentry_integrations = [DjangoIntegration()]
    try:
        from sentry_sdk.integrations.celery import CeleryIntegration

        _sentry_integrations.append(CeleryIntegration())
    except ImportError:
        pass

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=_sentry_integrations,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
        send_default_pii=False,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
    )

# --- Data Lifecycle & Privacy ---
DATA_RETENTION = {
    "audit_log_days": int(os.getenv("RETENTION_AUDIT_DAYS", "365")),
    "access_log_days": int(os.getenv("RETENTION_ACCESS_DAYS", "180")),
    "session_days": int(os.getenv("RETENTION_SESSION_DAYS", "90")),
    "report_days": int(os.getenv("RETENTION_REPORT_DAYS", "365")),
}

# --- Performance & Scaling ---
COMPLIANCE_DASHBOARD_CACHE_SECONDS = int(
    os.getenv("COMPLIANCE_DASHBOARD_CACHE_SECONDS", "60")
)
COMPLIANCE_EXPORT_MAX_ROWS = int(os.getenv("COMPLIANCE_EXPORT_MAX_ROWS", "5000"))

# --- Threat Detection & Incident Response ---
THREAT_DETECTION = {
    "window_minutes": int(os.getenv("THREAT_WINDOW_MINUTES", "60")),
    "failed_per_user": int(os.getenv("THREAT_FAILED_PER_USER", "10")),
    "failed_per_ip": int(os.getenv("THREAT_FAILED_PER_IP", "20")),
    "after_hours_start": int(os.getenv("THREAT_AFTER_HOURS_START", "22")),
    "after_hours_end": int(os.getenv("THREAT_AFTER_HOURS_END", "6")),
    "after_hours_threshold": int(os.getenv("THREAT_AFTER_HOURS_THRESHOLD", "5")),
    "mute_minutes": int(os.getenv("THREAT_MUTE_MINUTES", "0")),
}

INCIDENT_RESPONSE = {
    "oncall_emails": [e for e in os.getenv("ONCALL_EMAILS", "").split(",") if e],
    "ticket_webhook": os.getenv("INCIDENT_TICKET_WEBHOOK", ""),
    "playbook_url": os.getenv(
        "INCIDENT_PLAYBOOK_URL",
        "https://runbooks.runmycampus.com/security/incident-response",
    ),
}

# --- IP/Country Access Control ---
ENABLE_IP_COUNTRY_ACCESS_CONTROL = (
    os.getenv("ENABLE_IP_COUNTRY_ACCESS_CONTROL", "1") == "1"
)
BYPASS_ACCESS_CONTROL_FOR_SUPERUSERS = (
    os.getenv("BYPASS_ACCESS_CONTROL_FOR_SUPERUSERS", "1") == "1"
)

# --- Rate Limiting ---
RATELIMIT_ENABLE = os.getenv("RATELIMIT_ENABLE", "1") == "1"
RATELIMIT_USE_CACHE = "default"  # Use Django cache backend
RATELIMIT_VIEW = (
    "apps.compliance.views_ratelimit.ratelimit_error"  # Custom error handler
)


# ============================================================================
# Phase 1.2.4: Internationalization & Multi-Region Support
# ============================================================================

# --- Django i18n Settings ---
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "en")
LANGUAGES = [
    ("en", "English"),
    ("es", "Español (Spanish)"),
    ("fr", "Français (French)"),
    ("pt-br", "Português Brasil"),
    ("de", "Deutsch (German)"),
    ("it", "Italiano (Italian)"),
    ("ru", "Русский (Russian)"),
    ("tr", "Türkçe (Turkish)"),
    ("ja", "日本語 (Japanese)"),
    ("zh-hans", "简体中文 (Chinese Simplified)"),
    ("zh-hant", "繁體中文 (Chinese Traditional)"),
    ("hi", "हिन्दी (Hindi)"),
    ("ar", "العربية (Arabic)"),
    ("pid", "Pidgin English"),
    ("sw", "Kiswahili"),
    ("ha", "Hausa"),
    ("yo", "Yoruba"),
    ("he", "עברית (Hebrew)"),
    ("fa", "فارسی (Persian)"),
    ("ur", "اردو (Urdu)"),
]

# Register custom language codes in Django's LANG_INFO so get_language_info() (e.g. admin/unfold language switch) does not raise KeyError.
import django.conf.locale

EXTRA_LANG_INFO = {
    "pid": {
        "bidi": False,
        "code": "pid",
        "name": "Pidgin English",
        "name_local": "Pidgin",
    },
    "sw": {"bidi": False, "code": "sw", "name": "Kiswahili", "name_local": "Kiswahili"},
    "ha": {"bidi": False, "code": "ha", "name": "Hausa", "name_local": "Hausa"},
    "yo": {"bidi": False, "code": "yo", "name": "Yoruba", "name_local": "Yorùbá"},
    "he": {"bidi": True, "code": "he", "name": "Hebrew", "name_local": "עברית"},
    "fa": {"bidi": True, "code": "fa", "name": "Persian", "name_local": "فارسی"},
    "ur": {"bidi": True, "code": "ur", "name": "Urdu", "name_local": "اردو"},
}
django.conf.locale.LANG_INFO = {**django.conf.locale.LANG_INFO, **EXTRA_LANG_INFO}

# Use TIME_ZONE in .env for local schedules (e.g. Africa/Douala, America/New_York, Europe/London, UTC).
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")
LOCALE_PATHS = [
    BASE_DIR / "locale",
]

# --- Multi-Region Configuration ---
# Phase 12: no hardcoded region/currency/grading; bootstrap from registries. Set in .env if needed.
REGION_CODE = os.getenv("REGION_CODE", "")
DEFAULT_GRADING_SCALE = os.getenv("DEFAULT_GRADING_SCALE", "")
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "")
# When True: region switcher can be shown in UI and users can switch region in session.
# When False: single region per deployment (use REGION_CODE). Used in context as enable_multi_region.
ENABLE_MULTI_REGION = os.getenv("ENABLE_MULTI_REGION", "False").lower() == "true"

# Platform-neutral fallbacks when no tenant/region context (global reach; no single-country default). Used by get_platform_defaults().
# When REGION_CODE/DEFAULT_CURRENCY/DEFAULT_GRADING_SCALE are set in .env they are used; otherwise neutral defaults.
PLATFORM_DEFAULT_REGION_CODE = (
    os.getenv("PLATFORM_DEFAULT_REGION_CODE", "") or REGION_CODE or "GLOBAL"
)
PLATFORM_DEFAULT_CURRENCY = (
    os.getenv("PLATFORM_DEFAULT_CURRENCY", "") or DEFAULT_CURRENCY or "USD"
)
PLATFORM_DEFAULT_TIMEZONE = (
    os.getenv("PLATFORM_DEFAULT_TIMEZONE", "") or TIME_ZONE or "UTC"
)
PLATFORM_DEFAULT_GRADING_SCALE = (
    os.getenv("PLATFORM_DEFAULT_GRADING_SCALE", "") or DEFAULT_GRADING_SCALE or "0-100"
)

# Platform palette defaults — fallback hex values used when a tenant has not configured
# their brand palette via SiteSettings. Consumed by:
#   - apps.siteconfig.email_palette.resolve_email_palette() for transactional emails
#   - apps.siteconfig.platform_palette.platform_palette_processor for template context
#     (templates use `{{ platform_palette.primary }}` instead of `|default:'#4f46e5'`)
# Operators that white-label the platform set these via env (e.g. PLATFORM_PALETTE_PRIMARY=#0f172a)
# so even the "pre-tenant" UI surfaces (signup, palette selector swatches) reflect their brand.
PLATFORM_PALETTE_PRIMARY = os.getenv("PLATFORM_PALETTE_PRIMARY", "#4f46e5")
PLATFORM_PALETTE_ACCENT = os.getenv("PLATFORM_PALETTE_ACCENT", "#10b981")
PLATFORM_PALETTE_SURFACE = os.getenv("PLATFORM_PALETTE_SURFACE", "#ffffff")
PLATFORM_PALETTE_DASHBOARD_BG = os.getenv("PLATFORM_PALETTE_DASHBOARD_BG", "#f8fafc")
PLATFORM_PALETTE_HERO_BG = os.getenv("PLATFORM_PALETTE_HERO_BG", "#0f172a")
PLATFORM_PALETTE_MUTED_SWATCH = os.getenv("PLATFORM_PALETTE_MUTED_SWATCH", "#f0f0f0")
PLATFORM_PALETTE_BORDER_LIGHT = os.getenv("PLATFORM_PALETTE_BORDER_LIGHT", "#cccccc")
PLATFORM_PALETTE_SUCCESS = os.getenv("PLATFORM_PALETTE_SUCCESS", "#22c55e")
PLATFORM_PALETTE_WARNING = os.getenv("PLATFORM_PALETTE_WARNING", "#f59e0b")
PLATFORM_PALETTE_DANGER = os.getenv("PLATFORM_PALETTE_DANGER", "#ef4444")

# Risk-band fallback thresholds (used by apps.analytics.get_risk_band_for_school and
# RiskFactor.band when a tenant has not configured RiskThresholds). The defaults assume
# the platform PLATFORM_DEFAULT_GRADING_SCALE; tenants on alternate scales (0-20, GPA,
# letter) should configure RiskThresholds per-school rather than rely on these.
RISK_BAND_RED_MIN = float(os.getenv("RISK_BAND_RED_MIN", "80"))
RISK_BAND_AMBER_MIN = float(os.getenv("RISK_BAND_AMBER_MIN", "50"))

# Optional global cap on a single payment amount in the smallest currency unit.
# Default 100 billion minor units accommodates low-denomination currencies (IDR, VND, IRR).
# Override per deployment when stricter limits apply.
PAYMENT_MAX_AMOUNT = int(os.getenv("PAYMENT_MAX_AMOUNT", "100000000000"))

# Global grading scales (imported from apps.evals.grading module at runtime)
# Reference: GRADING_SCALES, CURRENCY_SYMBOLS defined in apps/evals/grading.py

# FX table for reporting + CurrencyLocalization (units per 1 USD unless FROM_TO pair keys).
EXCHANGE_RATES = {
    "BASE": "USD",
    "USD": 1,
    "EUR": 0.92,
    "GBP": 0.79,
    "NGN": 1550,
    "KES": 130,
    "XAF": 600,
    "ZAR": 18.5,
    "CNY": 7.2,
    "THB": 36,
}
# Wall-clock request cap for WSGI (0 = disabled). Rural / high-latency UX; see RequestTimeoutMiddleware.
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))

# --- AI Gateway (RunMyCampus Open-Source AI Adoption Blueprint) ---
# All product AI goes through services.ai_gateway. No browser calls Ollama/vLLM/LiteLLM directly.
# In-product chat (general_chat): Ollama + rules only — Google Gemini removed; see docs/OLLAMA_OPERATIONS_AND_UPDATES.md.
AI_GATEWAY_ENABLED = os.getenv("AI_GATEWAY_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
# Per-tenant daily request cap; 0 = disabled. Env: AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY
AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY = int(
    os.getenv("AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY", "0")
)
# Default gateway inference follows RMC_DEPLOYMENT_PROFILE (services.ai_deployment_posture):
# online + LITELLM_PROXY_URL → litellm, ollama, rules; edge/hybrid → ollama, rules (hybrid adds litellm when configured).
# Optional: merge per task via settings.AI_GATEWAY_TASK_TIERS dict (not env string).
# VLLM_ENDPOINT, VLLM_MODEL / LITELLM_PROXY_URL, LITELLM_MODEL only apply when those tiers are enabled.
# Embeddings default to Ollama when AI_EMBEDDING_BACKEND is unset (services/embeddings.py).
# AI_EMBEDDING_BACKEND=ollama|openai_compatible; AI_EMBEDDING_ENDPOINT, AI_EMBEDDING_MODEL, AI_EMBEDDING_API_KEY
# Request metadata: sensitivity_class, latency_target, output_type, allowed_backends (see ai_orchestration.md)
# Optional: internal Open WebUI URL for Control Plane "AI Ops" link (env: OPEN_WEBUI_URL)
OPEN_WEBUI_URL = os.getenv("OPEN_WEBUI_URL", "").strip() or None

# Online (Render) | edge (LAN hub) | hybrid (Render + hub_base_url fallback). See docs/LOCAL_HUB_MODE.md.
RMC_DEPLOYMENT_PROFILE = (
    os.getenv("RMC_DEPLOYMENT_PROFILE", "online").strip().lower() or "online"
)
RMC_HUB_BASE_URL = (os.getenv("RMC_HUB_BASE_URL", "") or "").strip().rstrip("/")
RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION = os.getenv(
    "RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION", "1"
).strip().lower() in ("1", "true", "yes", "on")
# Premium cloud tier (OpenAI-compatible). Option A default: one model + rules fallback (docs/AI_DEPLOYMENT_POSTURE.md).
# OpenAI direct: LITELLM_PROXY_URL=https://api.openai.com (not platform.openai.com).
LITELLM_PROXY_URL = (os.getenv("LITELLM_PROXY_URL", "") or "").strip().rstrip("/")
LITELLM_MODEL = (os.getenv("LITELLM_MODEL", "") or "gpt-5.4-mini").strip()
LITELLM_API_KEY = (os.getenv("LITELLM_API_KEY", "") or "").strip()

# Support ticket AI: prepend tenant KB/FAQ excerpts to ``support_suggest`` prompts (1 = on).
SUPPORT_AI_KB_CONTEXT = os.getenv("SUPPORT_AI_KB_CONTEXT", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
# KB RAG: auto-refresh embeddings on publish (batch 1341); pgvector path when column exists (1351).
KB_EMBEDDING_AUTO_REFRESH = os.getenv("KB_EMBEDDING_AUTO_REFRESH", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
KB_PGVECTOR_ENABLED = os.getenv("KB_PGVECTOR_ENABLED", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# First-line support engine room (RAG + topology + constrained Ollama persona).
AI_ENGINE_ROOM_SUPPORT = os.getenv("AI_ENGINE_ROOM_SUPPORT", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
AI_ENGINE_ROOM_TIMEOUT_SECONDS = int(os.getenv("AI_ENGINE_ROOM_TIMEOUT_SECONDS", "15"))
AI_ENGINE_ROOM_MAX_INPUT_TOKENS = int(os.getenv("AI_ENGINE_ROOM_MAX_INPUT_TOKENS", "6000"))
# Legacy label for engine-room dashboards; tier routing uses ai_deployment_posture + ai_gateway.
AI_GATEWAY_PROVIDER = (os.getenv("AI_GATEWAY_PROVIDER", "ollama") or "ollama").strip().lower()
AI_ALLOW_RULES_FALLBACK = os.getenv("AI_ALLOW_RULES_FALLBACK", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
OLLAMA_BASE_URL = (os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434") or "http://127.0.0.1:11434").strip().rstrip("/")
OLLAMA_MODEL = (os.getenv("OLLAMA_MODEL", "ai-center-master") or "ai-center-master").strip()
# Probe common dev hosts (127.0.0.1, localhost, host.docker.internal, WSL gateway) when unset or unreachable.
OLLAMA_AUTO_DISCOVER = os.getenv("OLLAMA_AUTO_DISCOVER", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# Optional comma-separated extra bases, e.g. http://192.168.1.10:11434
OLLAMA_BASE_URL_CANDIDATES = (os.getenv("OLLAMA_BASE_URL_CANDIDATES", "") or "").strip()
# Optional strict posture: block rules fallback and return explicit unavailable copy (off by default).
OLLAMA_REQUIRE_LIVE = os.getenv("OLLAMA_REQUIRE_LIVE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# Best-effort ``ollama serve`` when inference runs and the daemon is down (dev/on-prem; off in cloud).
_OLLAMA_AUTO_START_DEFAULT = (
    "0"
    if (RUNNING_TESTS or _IS_CLOUD_DEPLOYED)
    else ("1" if DEBUG else "0")
)
OLLAMA_AUTO_START = os.getenv("OLLAMA_AUTO_START", _OLLAMA_AUTO_START_DEFAULT).strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
AI_CENTER_LOG_PROMPTS = os.getenv("AI_CENTER_LOG_PROMPTS", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
AI_CENTER_MAX_CONTEXT_DOCS = int(os.getenv("AI_CENTER_MAX_CONTEXT_DOCS", "8"))
AI_CENTER_TIMEOUT_SECONDS = int(os.getenv("AI_CENTER_TIMEOUT_SECONDS", "30"))
ENABLE_AI_KNOWLEDGE_INDEX_BEAT = os.getenv(
    "ENABLE_AI_KNOWLEDGE_INDEX_BEAT", "0"
).strip().lower() in ("1", "true", "yes")
# After portal support form creates a GlobalSupportTicket, enqueue async triage (Celery worker required).
SUPPORT_AI_AUTO_TRIAGE_ON_CREATE = os.getenv(
    "SUPPORT_AI_AUTO_TRIAGE_ON_CREATE", "0"
).strip().lower() in ("1", "true", "yes")
# Zero-result help search → auto KB draft when hit_count reaches threshold (HITL publish still required).
HELP_ZERO_RESULT_AUTO_DRAFT_KB = os.getenv(
    "HELP_ZERO_RESULT_AUTO_DRAFT_KB", "0"
).strip().lower() in ("1", "true", "yes")
HELP_ZERO_RESULT_AUTO_DRAFT_HITS = int(
    os.getenv("HELP_ZERO_RESULT_AUTO_DRAFT_HITS", "5") or "5"
)
# Product MCP HTTP scaffold (batch 1395). Enable when external MCP client credentials are ready.
RMC_PRODUCT_MCP_ENABLED = os.getenv(
    "RMC_PRODUCT_MCP_ENABLED", "0"
).strip().lower() in ("1", "true", "yes")
# New GlobalSupportTicket: email all IT_ADMIN / fallback operator pool (1 = on).
SUPPORT_TICKET_NOTIFY_EMAIL = os.getenv(
    "SUPPORT_TICKET_NOTIFY_EMAIL", "1"
).strip().lower() in ("1", "true", "yes")
# Additional in-app Messages to operators (excluding primary Message recipient).
SUPPORT_TICKET_NOTIFY_INAPP = os.getenv(
    "SUPPORT_TICKET_NOTIFY_INAPP", "1"
).strip().lower() in ("1", "true", "yes")
# When true, create one Message per operator (noisy). Default off: operators rely on digest email.
SUPPORT_TICKET_INAPP_FANOUT_OPERATORS = os.getenv(
    "SUPPORT_TICKET_INAPP_FANOUT_OPERATORS", "0"
).strip().lower() in ("1", "true", "yes")
# Email tenant submitter when an operator posts a SUBMITTER_VISIBLE reply (not when they add their own follow-up).
SUPPORT_TICKET_NOTIFY_SUBMITTER_ON_VISIBLE_REPLY = os.getenv(
    "SUPPORT_TICKET_NOTIFY_SUBMITTER_ON_VISIBLE_REPLY", "1"
).strip().lower() in ("1", "true", "yes")
# Best-effort push (requires tenant push integration + device token on user). Off by default.
SUPPORT_TICKET_PUSH_SUBMITTER_ON_VISIBLE_REPLY = os.getenv(
    "SUPPORT_TICKET_PUSH_SUBMITTER_ON_VISIBLE_REPLY", "0"
).strip().lower() in ("1", "true", "yes")
SUPPORT_TICKET_PUSH_OPERATORS_ON_CREATE = os.getenv(
    "SUPPORT_TICKET_PUSH_OPERATORS_ON_CREATE", "0"
).strip().lower() in ("1", "true", "yes")
# Optional signed POST (HMAC SHA256 header X-RunMyCampus-Signature) for integrations.
SUPPORT_TICKET_WEBHOOK_URL = os.getenv("SUPPORT_TICKET_WEBHOOK_URL", "").strip()
SUPPORT_TICKET_WEBHOOK_SECRET = os.getenv(
    "SUPPORT_TICKET_WEBHOOK_SECRET", ""
).strip()

# Ollama CLI: guarded pulls (sync_ollama_models command; optional Celery beat — opt-in).
OLLAMA_CLI_PATH = (os.getenv("OLLAMA_CLI_PATH", "ollama") or "ollama").strip()
try:
    _pull_to = int(os.getenv("OLLAMA_PULL_TIMEOUT_SECONDS", "3600"))
except ValueError:
    _pull_to = 3600
OLLAMA_PULL_TIMEOUT_SECONDS = max(60, min(_pull_to, 86400))

# --- Application Version ---
APP_VERSION = "3.2.1"  # System version for dashboard footer

# --- Phase I: Schema-per-tenant (django-tenants) — DEFAULT for PostgreSQL ---
# Two modes (mutually exclusive):
#   - USE_DJANGO_TENANTS=1 (PostgreSQL): TenantMainMiddleware + TenantSchemaSchoolBridgeMiddleware
#     resolve request.tenant/request.school from customers.Domain; tenant tables live in per-tenant schemas.
#   - USE_DJANGO_TENANTS=0 or non-PostgreSQL: TenantMiddleware resolves request.school from
#     School/SchoolDomain/subdomain; single schema with RLS.
# Set USE_DJANGO_TENANTS=0 to use shared table + RLS. See docs/PHASE_I_SCALE_GAP_ANALYSIS.md.
_db_engine = DATABASES.get("default", {}).get("ENGINE", "")
_use_tenants_env = os.getenv("USE_DJANGO_TENANTS", "").strip().lower()
if _use_tenants_env in ("0", "false", "no"):
    USE_DJANGO_TENANTS = False
elif _use_tenants_env in ("1", "true", "yes"):
    USE_DJANGO_TENANTS = _db_engine.endswith("postgresql")
else:
    USE_DJANGO_TENANTS = _db_engine.endswith(
        "postgresql"
    )  # Default: schema-per-tenant for PostgreSQL
# TENANCY_MODE: explicit SCHEMA | RLS (optional env override). Default derived from USE_DJANGO_TENANTS.
_tm_env = os.getenv("TENANCY_MODE", "").strip().upper()
if _tm_env in ("SCHEMA", "RLS"):
    TENANCY_MODE = _tm_env
    USE_DJANGO_TENANTS = TENANCY_MODE == "SCHEMA"
else:
    TENANCY_MODE = "SCHEMA" if USE_DJANGO_TENANTS else "RLS"

if USE_DJANGO_TENANTS and _db_engine.endswith("postgresql"):
    # Swap to django-tenants PostgreSQL backend
    _db = DATABASES["default"].copy()
    _db["ENGINE"] = "django_tenants.postgresql_backend"
    DATABASES["default"] = _db
    # Router: tenant DB alias (World Engine) then shared vs tenant apps
    DATABASE_ROUTERS = [
        "apps.siteconfig.db_router.TenantDatabaseRouter",
        "django_tenants.routers.TenantSyncRouter",
    ]
    # Tenant and domain models (apps.customers)
    TENANT_MODEL = "customers.Client"
    TENANT_DOMAIN_MODEL = "customers.Domain"
    SHOW_PUBLIC_IF_NO_TENANT_FOUND = True
    SHARED_APPS = [
        "django_tenants",
        "django.contrib.contenttypes",
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "unfold",
        "django_otp",
        "django_otp.plugins.otp_totp",
        "django_otp.plugins.otp_static",
        "rest_framework",
        "rest_framework_simplejwt",
        "rest_framework_simplejwt.token_blacklist",
        "apps.accounts",
        "apps.schools",
        "apps.security.apps.SecurityConfig",
        "apps.siteconfig",
        "apps.runtime_blueprints.apps.RuntimeBlueprintsConfig",  # Proxy-owner for DashboardWidget; required by reports
        "apps.global_registries.apps.GlobalRegistriesConfig",  # Proxy-owner for RegionConfig; required by compliance
        "apps.registries",
        "apps.compliance",
        "apps.observability.apps.ObservabilityConfig",
        "apps.api",
        "apps.sync_engine.apps.SyncEngineConfig",
        "apps.apicenter",
        "apps.automation",
        "apps.migration_cloud.apps.MigrationCloudConfig",
        "apps.requests",
        "apps.billing",
        "apps.sales.apps.SalesConfig",
        "apps.metadata.apps.MetadataConfig",
        "emis",
        "django_celery_results",
        "django_celery_beat",
        "apps.customers",
        "apps.tenancy",
        "apps.policies",
        "apps.events",
        "apps.marketplace",
        "apps.social_media.apps.SocialMediaConfig",  # Public-schema social OAuth + outbox (school FK nullable); migrate_schemas --shared
        "apps.integrations_marketplace.apps.IntegrationsMarketplaceConfig",  # Proxy owners + Celery OAuth/mailbox tasks; middleware
        "apps.setup_studio.apps.SetupStudioConfig",  # SetupStepDefinition + SetupProgress (school FK in public schema)
        "apps.packages.apps.PackagesConfig",  # Package engine (InstalledPackage, etc.) in public schema for manager package_rollout
        "apps.customersuccess",
        "apps.brand_experience.apps.BrandExperienceConfig",  # Admin IA references; required for platform admin app list
        "apps.orchestration.apps.OrchestrationConfig",  # Phase 10 long-running process; tables in public schema
        # Public-schema runtime state (RuntimeDefaults, PlatformEventLog, phase-B snapshots). Must be in SHARED_APPS
        # so migrate_schemas --shared loads these migrations; siteconfig.0162+ depend on this app.
        "apps.platform_runtime.apps.PlatformRuntimeConfig",
        "apps.dashboard.apps.DashboardConfig",
        # Public-schema School lifecycle spine (SchoolLifecycleStage on School FK; operator-surface rapid-create / migration-intent / offboarding).
        "apps.lifecycle.apps.LifecycleConfig",
    ]
    TENANT_APPS = [
        "apps.portal",
        "apps.academics",
        "apps.people",
        "apps.schoolops",
        "apps.finance",
        "apps.evals",
        "apps.reports",
        "apps.communication",
        "apps.feedback.apps.FeedbackConfig",
        "apps.analytics",
        "apps.payroll",
        "apps.school_events",
        "apps.student360",
        "apps.studio_os.apps.StudioOsConfig",  # Tenant/manager Studio OS routes (no models; views + services)
    ]
    INSTALLED_APPS = list(SHARED_APPS) + [
        a for a in TENANT_APPS if a not in SHARED_APPS
    ]
    # Middleware: TenantMain first (strict tenant resolution), then URLConf switch, then school bridge.
    MIDDLEWARE = [
        "django_tenants.middleware.main.TenantMainMiddleware",
        "apps.schools.middleware.LegacyBaseDomainRedirectMiddleware",
        "apps.schools.middleware.UrlConfSwitcherMiddleware",
        "apps.schools.middleware.ReservedPublicHostAccessMiddleware",
        "apps.schools.middleware.PublicPathRedirectMiddleware",
        "apps.schools.middleware.TenantSchemaSchoolBridgeMiddleware",
        "apps.schools.middleware_session_school_bind.SessionSchoolBindingMiddleware",
        "apps.schools.middleware.TenantSchoolNotFoundMiddleware",
        "apps.tenancy.middleware.TenantContextMiddleware",  # Attach request.tenant_ctx (TenantContext)
        "apps.platform_runtime.middleware.TenantRuntimeMiddleware",  # Attach request.tenant_runtime (TenantRuntime)
        "django.middleware.security.SecurityMiddleware",
        "config.middleware.BlockScannerPathsMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        "apps.accounts.middleware.ManagerCookieIsolationMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "apps.accounts.middleware_session_pinning.SessionPinningMiddleware",
        "apps.schools.middleware_conversion_lock.ConversionLockMiddleware",
        "apps.schools.growth_funnel_middleware.GrowthFunnelMiddleware",
        "apps.schools.middleware_activation_gate.ActivationGateMiddleware",
        "apps.marketplace.middleware.AppApiContextMiddleware",
        "apps.accounts.middleware.ImpossibleTravelMiddleware",
        "apps.accounts.middleware.RoleBasedSessionTimeoutMiddleware",
        "apps.schools.middleware.ManagerHostControlPlaneRequiredMiddleware",
        "apps.schools.middleware_dashboard_topology.DashboardTopologyRBACMiddleware",
        "apps.accounts.middleware.ModuleAccessMiddleware",
        "apps.accounts.middleware.RequireMFAMiddleware",
        "apps.schools.middleware.TenantFreezeMiddleware",
        "apps.schools.middleware.SentryTenantTagMiddleware",
        "apps.schools.middleware.TenantLastActivityMiddleware",
        "apps.schools.middleware.TenantApiQuotaMiddleware",
        "config.middleware.GlobalHotPathRateLimitMiddleware",
        "apps.schools.middleware.DynamicThemeMiddleware",
        "apps.schools.middleware.TenantSuperAdminRequiredMiddleware",
        "apps.schools.middleware.FeatureGatekeeperMiddleware",
        "apps.schools.middleware.UsageLimitMiddleware",
        "django_otp.middleware.OTPMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "apps.siteconfig.middleware.MaintenanceModeMiddleware",
        "apps.siteconfig.middleware.preview_mode.PreviewModeMiddleware",
        "apps.compliance.middleware.IPCountryAccessMiddleware",
        "apps.compliance.middleware.AuditLoggingMiddleware",
        "apps.compliance.middleware.AccessControlMiddleware",
        "apps.observability.middleware.RequestIdLoggingMiddleware",
        "apps.observability.middleware.ObservabilityMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
    # TenantMiddleware is not used; TenantMainMiddleware + TenantSchemaSchoolBridgeMiddleware provide request.school

# Tenant lifecycle automation (retention playbooks + churn thresholds); numbers are env-overridable.
TENANT_LIFECYCLE_CHURN_PAYMENT_FAILED_DAYS = int(
    os.getenv("TENANT_LIFECYCLE_CHURN_PAYMENT_FAILED_DAYS", "30")
)
TENANT_LIFECYCLE_CHURN_INACTIVITY_DAYS = int(
    os.getenv("TENANT_LIFECYCLE_CHURN_INACTIVITY_DAYS", "90")
)
TENANT_LIFECYCLE_ONBOARDING_STALL_DAYS = int(
    os.getenv("TENANT_LIFECYCLE_ONBOARDING_STALL_DAYS", "7")
)
TENANT_LIFECYCLE_FIRST_ACTION_STALL_DAYS = int(
    os.getenv("TENANT_LIFECYCLE_FIRST_ACTION_STALL_DAYS", "14")
)

# ---------------------------------------------------------------------------
# Runtime constants — pulled from config/runtime_constants.py so app code can
# use settings.HTTP_OUTBOUND_TIMEOUT_STANDARD, settings.DEFAULT_PAGE_SIZE, etc.
# See docs/CONFIGURABILITY.md (Layer B).
# ---------------------------------------------------------------------------
from config.runtime_constants import (  # noqa: E402
    HTTP_OUTBOUND_TIMEOUT_SHORT,
    HTTP_OUTBOUND_TIMEOUT_STANDARD,
    HTTP_OUTBOUND_TIMEOUT_LONG,
    HTTP_OUTBOUND_TIMEOUT_BATCH,
    DEFAULT_TASK_MAX_RETRIES,
    DEFAULT_TASK_RETRY_BACKOFF_SECONDS,
    WELCOME_EMAIL_MAX_RETRIES,
    OFFLINE_SYNC_MAX_RETRIES,
    CACHE_TTL_SHORT,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_LONG,
    CACHE_TTL_DAY,
    CACHE_TTL_WEEK,
    CACHE_TTL_MONTH,
    CACHE_TTL_QUARTER,
    CACHE_TTL_YEAR,
    DEFAULT_ADMIN_PAGE_SIZE,
    DEFAULT_AUDIT_PAGE_SIZE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_WIDGET_PAGE_SIZE,
    MAX_PHOTO_UPLOAD_BYTES,
    MAX_DOCUMENT_UPLOAD_BYTES,
    MAX_CSV_IMPORT_BYTES,
    GRADE_WEIGHT_SEQ1,
    GRADE_WEIGHT_SEQ2,
    GRADE_WEIGHT_EXAM,
    GRADE_WEIGHT_MOCK,
    GRADE_WEIGHT_PRACTICAL,
    default_grade_weights,
)
