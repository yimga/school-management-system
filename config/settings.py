from pathlib import Path
import os
import sys
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()
# .env.local: do not override vars already set (e.g. DATABASE_URL on Render), so local file only fills in unset keys.
load_dotenv(BASE_DIR / ".env.local", override=False)

from django.core.exceptions import ImproperlyConfigured

SECRET_KEY = os.getenv("SECRET_KEY")
_is_render = os.getenv("RENDER", "").lower() == "true"
_debug_default = "0" if _is_render else "1"
DEBUG = os.getenv("DEBUG", _debug_default) == "1"
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
_multi_tenant_base = os.getenv(
    "MULTI_TENANT_BASE_DOMAIN",
    "runmycampus.com",
).strip().lower()
_legacy_bases_raw = (
    os.getenv("MULTI_TENANT_LEGACY_BASE_DOMAINS")
    or ""
).strip().lower()
_legacy_bases = [d.strip() for d in _legacy_bases_raw.split(",") if d.strip()]
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
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be configured for production.")

# Behind HTTPS proxy (e.g. Render, Heroku): trust X-Forwarded-Proto so request.is_secure() and CSRF work
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# CSRF: allow HTTPS origins (Django 4.0+). On Render, set CSRF_TRUSTED_ORIGINS or RENDER_EXTERNAL_HOSTNAME is used.
_csrf_origins = os.getenv("CSRF_TRUSTED_ORIGINS", "").strip()
_render_host = (os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip()
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [s.strip() for s in _csrf_origins.split(",") if s.strip()]
elif _render_host:
    CSRF_TRUSTED_ORIGINS = [f"https://{_render_host}"]
else:
    CSRF_TRUSTED_ORIGINS = []
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

    # Django Channels (for WebSocket support) - Optional
    # Uncomment and install: pip install channels channels-redis
    # "channels",
    # "channels_redis",

    # Django OTP (MFA)
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",

    # REST Framework
    "rest_framework",
    "rest_framework_simplejwt",

    # Project apps
    "apps.accounts.apps.AccountsConfig",
    "apps.customers",
    "apps.evals",
    "apps.portal",
    "apps.academics",
    "apps.people",
    "apps.reports",
    "apps.siteconfig.apps.SiteconfigConfig",
    "apps.schools",
    "apps.analytics",
    "apps.finance",
    "apps.payroll",
    "apps.compliance.apps.ComplianceConfig",
    "apps.communication",
    "apps.requests",
    "apps.observability",  # Observability/monitoring
    "apps.api",
    "apps.apicenter",
    "apps.automation",  # Automation and background tasks
    "emis",
    # Celery result/beat (optional: used when REDIS_URL is set for background tasks)
    "django_celery_results",
    "django_celery_beat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.schools.middleware.LegacyBaseDomainRedirectMiddleware",  # Optional legacy-domain redirect middleware
    "apps.schools.middleware.UrlConfSwitcherMiddleware",  # Public vs tenant URLConf from host/path
    "apps.schools.middleware.ReservedPublicHostAccessMiddleware",  # verify./support. host isolation
    "apps.schools.middleware.PublicPathRedirectMiddleware",  # public paths hit on tenant host -> base host
    "apps.schools.middleware.TenantMiddleware",  # Multi-tenant: resolve request.school from subdomain/custom domain
    "apps.schools.middleware.TenantFreezeMiddleware",  # Section 8.6: redirect frozen schools to /account-frozen/
    "apps.schools.middleware.SentryTenantTagMiddleware",  # Phase H: tag Sentry with school_id
    "apps.schools.middleware.TenantLastActivityMiddleware",  # Phase H: optional last_activity per tenant
    "apps.schools.middleware.TenantApiQuotaMiddleware",  # Plan I: per-tenant API rate limit
    "apps.schools.middleware.DynamicThemeMiddleware",  # Phase B: admin theme per school (Unfold/Jazzmin/Sneat)
    "django.middleware.locale.LocaleMiddleware",  # Add for i18n
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.RoleBasedSessionTimeoutMiddleware",
    "apps.accounts.middleware.ModuleAccessMiddleware",
    "apps.accounts.middleware.RequireMFAMiddleware",
    "apps.schools.middleware.TenantSuperAdminRequiredMiddleware",  # Restrict /super/ to SUPERADMIN
    "apps.schools.middleware.FeatureGatekeeperMiddleware",  # Phase D: enforce plan feature by path
    "apps.schools.middleware.UsageLimitMiddleware",  # Phase D (optional, on by default): Plan max_students/max_staff; set DISABLE_USAGE_LIMIT_MIDDLEWARE=1 to turn off
]
MIDDLEWARE += [
    "apps.compliance.middleware.ComplianceGuardMiddleware",  # Phase Compliance: region → feature_code RESTRICTED/DISABLED
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.siteconfig.middleware.MaintenanceModeMiddleware",
    "apps.siteconfig.middleware.preview_mode.PreviewModeMiddleware",
    # Phase 4: Audit & Monitoring middleware
    "apps.compliance.middleware.IPCountryAccessMiddleware",  # IP/Country access control (first!)
    "apps.compliance.middleware.AuditLoggingMiddleware",  # Log all HTTP requests
    "apps.compliance.middleware.AccessControlMiddleware",  # Enforce access control
    # Phase 5: Observability middleware
    "apps.observability.middleware.ObservabilityMiddleware",  # Prometheus request metrics
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
PUBLIC_SCHEMA_URLCONF = "config.public_urls"
TENANT_SCHEMA_URLCONF = "config.tenant_urls"
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
                "apps.siteconfig.breadcrumb_context.breadcrumbs_context",
                "apps.siteconfig.breadcrumb_context.page_metadata_context",
                "apps.siteconfig.context_processors.region_settings",
                "apps.siteconfig.context_processors.language_context",
                "apps.accounts.context_processors.dashboard_context",  # Dashboard header/footer data
                "apps.portal.context_processors.announcements",  # Global announcements banner
                "apps.siteconfig.context_processors.ai_copilot_settings",  # AI Copilot API key
            ]
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# ASGI Application (WebSocket support) - Optional, requires channels
# Uncomment after installing: pip install channels channels-redis
# ASGI_APPLICATION = "config.asgi.application"

# Channels configuration (WebSocket support) - Optional
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {
#             "hosts": [os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1")],
#         },
#     },
# }
# 
# # Fallback to in-memory channel layer if Redis is not available
# if not os.getenv("REDIS_URL"):
#     CHANNEL_LAYERS = {
#         "default": {
#             "BACKEND": "channels.layers.InMemoryChannelLayer"
#         }
#     }

# --- Database ---

import os
from urllib.parse import quote_plus
import dj_database_url

# Treat empty or whitespace-only as unset (avoids dj_database_url returning incomplete config)
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip() or None
# Build DATABASE_URL from separate vars if set (e.g. Render injects DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT)
# Skip if DB_HOST looks like a placeholder (e.g. "from_render") and no real URL is available
if not DATABASE_URL and os.getenv("DB_HOST"):
    _db_host = (os.getenv("DB_HOST") or "").strip()
    if _db_host and _db_host not in ("from_render", "from_render ", ""):
        _db_user = os.getenv("DB_USER", "")
        _db_pass = os.getenv("DB_PASSWORD", "")
        _db_port = os.getenv("DB_PORT", "5432")
        _db_name = os.getenv("DB_NAME", "gilead_school_mgmt_db")
        _db_pass_enc = quote_plus(_db_pass) if _db_pass else ""
        _db_user_enc = quote_plus(_db_user) if _db_user else ""
        DATABASE_URL = f"postgresql://{_db_user_enc}:{_db_pass_enc}@{_db_host}:{_db_port}/{_db_name}"
PREVIEW_DATABASE_URL = (os.getenv("PREVIEW_DATABASE_URL") or "").strip() or None

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
            db_path = Path(os.getenv("LOCALAPPDATA")) / "GileadTechHigh" / "db_working.sqlite3"
        else:
            db_path = BASE_DIR / "db_working.sqlite3"
    else:
        sqlite_name = os.path.expanduser(os.path.expandvars(raw_db_file))
        db_path = Path(sqlite_name) if os.path.isabs(sqlite_name) else (BASE_DIR / sqlite_name)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(db_path),
        }
    }

if PREVIEW_DATABASE_URL:
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

# PERFORMANCE: Enable persistent database connections (600 seconds = 10 minutes)
# Reduces overhead of creating new connection for each request
for db_config in DATABASES.values():
    db_config["CONN_MAX_AGE"] = 600

DATABASE_ROUTERS = ["apps.siteconfig.db_router.PreviewDatabaseRouter"]

MARKSHEET_OCR_COMMAND = os.getenv("MARKSHEET_OCR_COMMAND", "")


AUTH_USER_MODEL = "accounts.User"

# --- Static / Media ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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
    DEFENDER_GET_USERNAME_FROM_REQUEST_PATH = "apps.accounts.defender_utils.get_username_from_request"
    DEFENDER_LOCK_OUT_BY_IP_OR_USERNAME = True
    DEFENDER_BEHIND_REVERSE_PROXY = os.getenv("RENDER", "0") == "1"
    DEFENDER_FAILURE_LIMIT = 5
    DEFENDER_COOLOFF_TIME = 60 * 15  # 15 minutes
    DEFENDER_DISABLE_IP_LOCKOUT = False
    INSTALLED_APPS.append("defender")
    _auth_idx = next((i for i, m in enumerate(MIDDLEWARE) if "AuthenticationMiddleware" in m), len(MIDDLEWARE))
    MIDDLEWARE.insert(_auth_idx, "defender.middleware.FailedLoginMiddleware")

# --- Site behavior ---
MAINTENANCE_MODE = False

# Render terminates TLS at the edge. Internal platform probes may hit HTTP
# without X-Forwarded-Proto and get redirected, which can break startup scans.
_secure_ssl_redirect_default = "0" if _is_render else "1"
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", _secure_ssl_redirect_default) == "1" and not DEBUG
# Test runner uses plain HTTP requests; keep HTTPS redirect behavior for runtime envs.
if "test" in sys.argv:
    SECURE_SSL_REDIRECT = False
# Health/readiness probes can come over plain HTTP from platform internals.
# Exempt these endpoints to avoid redirect loops and failed boot probes.
SECURE_REDIRECT_EXEMPT = [
    r"^$",
    r"^health/",
    r"^healthz/",
    r"^ready/",
    r"^status/",
    r"^api/health/",
    r"^api/caddy-check/",   # Section 8: Caddy on-demand TLS (often called over HTTP by Caddy)
    r"^discover/",          # Section 8: Global login discovery (landing page)
    r"^account-frozen/",    # Section 8: Frozen account page (may be hit before HTTPS)
]
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "1") == "1" and not DEBUG
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "1") == "1" and not DEBUG
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "60")) if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "1") == "1"
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "1") == "1"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
_session_cookie_domain_env = (os.getenv("SESSION_COOKIE_DOMAIN") or "").strip()
if _session_cookie_domain_env:
    SESSION_COOKIE_DOMAIN = _session_cookie_domain_env
elif _multi_tenant_base and _multi_tenant_base not in {"localhost", "127.0.0.1"}:
    SESSION_COOKIE_DOMAIN = f".{_multi_tenant_base}"
_csrf_cookie_domain_env = (os.getenv("CSRF_COOKIE_DOMAIN") or "").strip()
if _csrf_cookie_domain_env:
    CSRF_COOKIE_DOMAIN = _csrf_cookie_domain_env
elif _multi_tenant_base and _multi_tenant_base not in {"localhost", "127.0.0.1"}:
    CSRF_COOKIE_DOMAIN = f".{_multi_tenant_base}"
# Session expiry: use SESSION_INACTIVITY_TIMEOUT_MINUTES for shared computers (e.g. 15–30),
# or SESSION_COOKIE_AGE (seconds) for max session length. With SESSION_SAVE_EVERY_REQUEST=True,
# session expires after this many seconds of *inactivity* (no requests).
_session_inactivity_minutes = os.getenv("SESSION_INACTIVITY_TIMEOUT_MINUTES", "")
if _session_inactivity_minutes.strip():
    SESSION_COOKIE_AGE = int(_session_inactivity_minutes) * 60
else:
    SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "14400"))  # 4 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = os.getenv("SESSION_EXPIRE_AT_BROWSER_CLOSE", "1") == "1"
SESSION_SAVE_EVERY_REQUEST = os.getenv("SESSION_SAVE_EVERY_REQUEST", "1") == "1"

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
    "SITE_TITLE": "Gilead School Admin",
    "SITE_HEADER": "Gilead School Management",
    "SITE_SUBHEADER": "Gilead Tech High School",
    "SITE_URL": "/",

    # Icon/branding (32px height works best)
    "SITE_ICON": lambda request: static("images/logo.png"),

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
    "ip_whitelist": os.getenv("WEBHOOK_IP_WHITELIST", "").split(",") if os.getenv("WEBHOOK_IP_WHITELIST") else [],
}

# --- Observability ---
OBSERVABILITY_API_KEY = os.getenv("OBSERVABILITY_API_KEY", "")

# --- Payment Provider Configuration ---
# Each provider should have config in PaymentIntegration model:
# {
#     "webhook_secret": "api_key_from_provider",
#     "webhook_ips": ["1.2.3.4", "5.6.7.8"],
#     "rate_limit": 100,
#     "signature_header": "X-Signature"
# }

# --- Email Configuration ---
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@gileadschool.com")
# Optional regional SMTP (Phase Welcome): map region_id to from_email; override in local_settings, e.g. REGIONAL_FROM_EMAIL = {"DEU": "noreply@eu.example.com"}
REGIONAL_FROM_EMAIL = {}

# --- Caching Configuration ---
CACHES = {
    "default": {
        "BACKEND": os.getenv("CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
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
if REDIS_URL:
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"

# --- Celery (background tasks; broker uses REDIS_URL when set) ---
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or REDIS_URL or ""
CELERY_RESULT_BACKEND = "django-db"  # Store task results in Postgres; no Redis required for results
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = os.getenv("TIME_ZONE", "UTC")
CELERY_TASK_TRACK_STARTED = True
# Optional: run celery beat with: celery -A config beat -l info
# Add periodic tasks in Django admin (django_celery_beat) or define CELERY_BEAT_SCHEDULE (see Celery docs).

# Celery Beat schedule for periodic tasks
# Optional tasks (requests reminder, deadline reminder) respect Site Settings: 0 = no-op
CELERY_BEAT_SCHEDULE = {
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
}

# --- Logging Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Create logs directory if it doesn't exist (for file logging)
LOG_DIR = BASE_DIR / "logs"
USE_FILE_LOGGING = os.getenv("USE_FILE_LOGGING", str(DEBUG)) == "True"

# Only create logs directory if file logging is enabled
if USE_FILE_LOGGING:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except (OSError, PermissionError):
        # If we can't create the directory, disable file logging
        USE_FILE_LOGGING = False

# Build handlers list
LOGGING_HANDLERS = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "json" if os.getenv("LOG_JSON", "0") == "1" else "verbose",
        "level": LOG_LEVEL,
    },
}

# Add file handler only if file logging is enabled and directory exists
if USE_FILE_LOGGING:
    LOGGING_HANDLERS["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": LOG_DIR / "django.log",
        "maxBytes": 1024 * 1024 * 10,  # 10MB
        "backupCount": 10,
        "formatter": "json" if os.getenv("LOG_JSON", "0") == "1" else "verbose",
        "level": LOG_LEVEL,
    }

# Determine which handlers to use
ACTIVE_HANDLERS = ["console", "file"] if USE_FILE_LOGGING else ["console"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(levelname)s %(asctime)s %(name)s %(module)s %(process)d %(thread)d %(message)s",
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
            "level": "DEBUG" if DEBUG else "WARNING",
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
        "ACCESS_DENIED,DELETE,PERM_GRANT,PERM_REVOKE,APPROVE,REJECT"
    ).split(","),
    # Channels
    "email_recipients": [e for e in os.getenv("COMPLIANCE_ALERT_EMAILS", "").split(",") if e],
    "slack_webhook_url": os.getenv("COMPLIANCE_ALERT_SLACK_WEBHOOK", ""),
    "generic_webhook_url": os.getenv("COMPLIANCE_ALERT_WEBHOOK", ""),
    # Runbook / on-call guidance
    "runbook_url": os.getenv(
        "COMPLIANCE_RUNBOOK_URL",
        "https://runbooks.gileadschool.com/security/incident-response"
    ),
    # Scheduled compliance report recipients
    "report_recipients": [e for e in os.getenv("COMPLIANCE_REPORT_RECIPIENTS", "").split(",") if e],
    "report_email_enabled": os.getenv("COMPLIANCE_REPORT_EMAIL_ENABLED", "1") == "1",
}

# --- Sentry (error and performance monitoring) ---
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05"))
SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0"))

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
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
COMPLIANCE_DASHBOARD_CACHE_SECONDS = int(os.getenv("COMPLIANCE_DASHBOARD_CACHE_SECONDS", "60"))
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
        "https://runbooks.gileadschool.com/security/incident-response"
    ),
}

# --- IP/Country Access Control ---
ENABLE_IP_COUNTRY_ACCESS_CONTROL = os.getenv("ENABLE_IP_COUNTRY_ACCESS_CONTROL", "1") == "1"
BYPASS_ACCESS_CONTROL_FOR_SUPERUSERS = os.getenv("BYPASS_ACCESS_CONTROL_FOR_SUPERUSERS", "1") == "1"

# --- Rate Limiting ---
RATELIMIT_ENABLE = os.getenv("RATELIMIT_ENABLE", "1") == "1"
RATELIMIT_USE_CACHE = 'default'  # Use Django cache backend
RATELIMIT_VIEW = 'apps.compliance.views_ratelimit.ratelimit_error'  # Custom error handler


# ============================================================================
# Phase 1.2.4: Internationalization & Multi-Region Support
# ============================================================================

# --- Django i18n Settings ---
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGE_CODE = os.getenv('LANGUAGE_CODE', 'en')
LANGUAGES = [
    ('en', 'English'),
    ('fr', 'Français (French)'),
    ('pid', 'Pidgin English'),
    ('sw', 'Kiswahili'),
    ('ha', 'Hausa'),
    ('yo', 'Yoruba'),
]

# Register custom language codes in Django's LANG_INFO so get_language_info() (e.g. admin/unfold language switch) does not raise KeyError.
import django.conf.locale

EXTRA_LANG_INFO = {
    "pid": {"bidi": False, "code": "pid", "name": "Pidgin English", "name_local": "Pidgin"},
    "sw": {"bidi": False, "code": "sw", "name": "Kiswahili", "name_local": "Kiswahili"},
    "ha": {"bidi": False, "code": "ha", "name": "Hausa", "name_local": "Hausa"},
    "yo": {"bidi": False, "code": "yo", "name": "Yoruba", "name_local": "Yorùbá"},
}
django.conf.locale.LANG_INFO = {**django.conf.locale.LANG_INFO, **EXTRA_LANG_INFO}

# Buea/Cameroon: use TIME_ZONE=Africa/Douala in .env for local schedules and attendance
TIME_ZONE = os.getenv('TIME_ZONE', 'UTC')
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# --- Multi-Region Configuration ---
REGION_CODE = os.getenv('REGION_CODE', 'CMR')  # Default to Cameroon
DEFAULT_GRADING_SCALE = os.getenv('DEFAULT_GRADING_SCALE', '0-20')
DEFAULT_CURRENCY = os.getenv('DEFAULT_CURRENCY', 'XAF')
# When True: region switcher can be shown in UI and users can switch region in session.
# When False: single region per deployment (use REGION_CODE). Used in context as enable_multi_region.
ENABLE_MULTI_REGION = os.getenv('ENABLE_MULTI_REGION', 'False').lower() == 'true'

# Global grading scales (imported from apps.evals.grading module at runtime)
# Reference: GRADING_SCALES, CURRENCY_SYMBOLS defined in apps/evals/grading.py

# Optional: exchange rates for GET /api/v1/finance/exchange-rate (e.g. {"USD_XAF": 600, "BASE": "USD"} or Fixer.io key)
# EXCHANGE_RATES = {}

# --- Application Version ---
APP_VERSION = '3.2.1'  # System version for dashboard footer

# --- Phase I: Schema-per-tenant (django-tenants) — DEFAULT for PostgreSQL ---
# Default: schema-per-tenant when using PostgreSQL (RunMyCampus Gold Standard). Set USE_DJANGO_TENANTS=0 to use shared table + RLS.
# See docs/PHASE_I_SCALE_GAP_ANALYSIS.md.
_db_engine = DATABASES.get("default", {}).get("ENGINE", "")
_use_tenants_env = os.getenv("USE_DJANGO_TENANTS", "").strip().lower()
if _use_tenants_env in ("0", "false", "no"):
    USE_DJANGO_TENANTS = False
elif _use_tenants_env in ("1", "true", "yes"):
    USE_DJANGO_TENANTS = _db_engine.endswith("postgresql")
else:
    USE_DJANGO_TENANTS = _db_engine.endswith("postgresql")  # Default: schema-per-tenant for PostgreSQL
if USE_DJANGO_TENANTS and _db_engine.endswith("postgresql"):
    # Swap to django-tenants PostgreSQL backend
    _db = DATABASES["default"].copy()
    _db["ENGINE"] = "django_tenants.postgresql_backend"
    DATABASES["default"] = _db
    # Router: route shared vs tenant apps
    DATABASE_ROUTERS = ["django_tenants.routers.TenantSyncRouter"]
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
        "apps.accounts",
        "apps.schools",
        "apps.siteconfig",
        "apps.compliance",
        "apps.observability",
        "apps.api",
        "apps.apicenter",
        "apps.portal",
        "apps.automation",
        "apps.requests",
        "emis",
        "django_celery_results",
        "django_celery_beat",
        "apps.customers",
    ]
    TENANT_APPS = [
        "apps.academics",
        "apps.people",
        "apps.finance",
        "apps.evals",
        "apps.reports",
        "apps.communication",
        "apps.analytics",
        "apps.payroll",
    ]
    INSTALLED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]
    # Middleware: TenantMain first (strict tenant resolution), then URLConf switch, then school bridge.
    MIDDLEWARE = [
        "django_tenants.middleware.main.TenantMainMiddleware",
        "apps.schools.middleware.LegacyBaseDomainRedirectMiddleware",
        "apps.schools.middleware.UrlConfSwitcherMiddleware",
        "apps.schools.middleware.ReservedPublicHostAccessMiddleware",
        "apps.schools.middleware.PublicPathRedirectMiddleware",
        "apps.schools.middleware.TenantSchemaSchoolBridgeMiddleware",
        "apps.schools.middleware.TenantSchoolNotFoundMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "apps.accounts.middleware.RoleBasedSessionTimeoutMiddleware",
        "apps.accounts.middleware.ModuleAccessMiddleware",
        "apps.accounts.middleware.RequireMFAMiddleware",
        "apps.schools.middleware.TenantFreezeMiddleware",
        "apps.schools.middleware.SentryTenantTagMiddleware",
        "apps.schools.middleware.TenantLastActivityMiddleware",
        "apps.schools.middleware.TenantApiQuotaMiddleware",
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
        "apps.observability.middleware.ObservabilityMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
    # TenantMiddleware is not used; TenantMainMiddleware + TenantSchemaSchoolBridgeMiddleware provide request.school
