"""Central settings registry — single source of truth for documented settings.

Surface 9 closure: 238+ scattered ``getattr(settings, ...)`` calls across the
codebase had no central declaration. This file documents the intentional
surface so a verifier can flag any ``getattr(settings, X)`` whose name is not
listed here.

Adding a setting:

1. Pick a **scope** (security, payments, identity, ux, ops, …).
2. Add a row to ``SETTINGS_REGISTRY`` below with name, type, default, owner,
   purpose, and (optional) deprecation note.
3. Run ``python scripts/verify_settings_registry_coverage.py`` — fail if any
   call site references a name that isn't listed.

Naming rules:

- UPPER_SNAKE_CASE.
- Group related settings under a common prefix (``SECURE_``, ``STRIPE_``,
  ``MARKETING_ANALYTICS_``, ``RATE_LIMIT_``).
- Boolean flags end in ``_ENABLED`` / ``_REQUIRED`` / ``_ALLOWED`` for clarity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingSpec:
    name: str
    type: str
    default: str
    owner: str
    purpose: str
    deprecated_note: str = ""


# Initial seed — covers the settings I've added or hardened in this run.
# Future PRs extend this. The verifier flags references to undeclared names
# but does NOT fail on declared names that aren't yet referenced (the
# registry is the contract).
SETTINGS_REGISTRY: tuple[SettingSpec, ...] = (
    # Security headers
    SettingSpec(
        "SESSION_COOKIE_HTTPONLY",
        "bool",
        "True",
        "security",
        "Block JS access to the session cookie (XSS defense-in-depth).",
    ),
    SettingSpec(
        "CSRF_COOKIE_HTTPONLY",
        "bool",
        "True",
        "security",
        "Block JS access to the CSRF cookie.",
    ),
    SettingSpec(
        "X_FRAME_OPTIONS",
        "str",
        '"DENY"',
        "security",
        "Clickjacking protection.",
    ),
    SettingSpec(
        "SECURE_REFERRER_POLICY",
        "str",
        '"strict-origin-when-cross-origin"',
        "security",
        "Limit Referer header leakage.",
    ),
    SettingSpec(
        "SECURE_CROSS_ORIGIN_OPENER_POLICY",
        "str",
        '"same-origin"',
        "security",
        "COOP — isolate browsing context.",
    ),
    SettingSpec(
        "SECURE_CROSS_ORIGIN_RESOURCE_POLICY",
        "str",
        '"same-site"',
        "security",
        "CORP — Spectre-class side-channel mitigation.",
    ),
    SettingSpec(
        "SECURE_HSTS_SECONDS",
        "int",
        "31536000",
        "security",
        "HSTS lifetime in seconds (1 year).",
    ),
    # Incident routing
    SettingSpec(
        "ADMINS_EMAILS",
        "csv",
        '""',
        "ops",
        "Comma-separated emails that receive 500-error reports in production.",
    ),
    SettingSpec(
        "SERVER_EMAIL",
        "str",
        '"no-reply@runmycampus.com"',
        "ops",
        "From-address Django uses to email ADMINS on errors.",
    ),
    # MFA
    SettingSpec(
        "MFA_REQUIRED_ROLES_EXTRA",
        "tuple[str]",
        "()",
        "security",
        "Extra roles requiring MFA on top of the platform baseline.",
    ),
    # Rate limiting
    SettingSpec(
        "RATE_LIMIT_ENABLED",
        "bool",
        "True",
        "security",
        "Master switch for the per-endpoint rate limiter (apps.security.rate_limit).",
    ),
    # Payments — Stripe
    SettingSpec(
        "STRIPE_SECRET_KEY",
        "str",
        '""',
        "payments",
        "Live Stripe secret key (sk_live_*) — never log.",
    ),
    SettingSpec(
        "STRIPE_PUBLISHABLE_KEY",
        "str",
        '""',
        "payments",
        "Live Stripe publishable key (pk_live_*).",
    ),
    SettingSpec(
        "STRIPE_WEBHOOK_SECRET",
        "str",
        '""',
        "payments",
        "Stripe webhook signing secret.",
    ),
    # Payments — Paystack
    SettingSpec(
        "PAYSTACK_SECRET_KEY",
        "str",
        '""',
        "payments",
        "Live Paystack secret key (sk_live_*) — never log.",
    ),
    SettingSpec(
        "PAYSTACK_PUBLIC_KEY",
        "str",
        '""',
        "payments",
        "Live Paystack public key.",
    ),
    # Payments — Flutterwave
    SettingSpec(
        "FLUTTERWAVE_SECRET_KEY",
        "str",
        '""',
        "payments",
        "Live Flutterwave secret key (FLWSECK-…-X) — never log.",
    ),
    SettingSpec(
        "FLW_SECRET_HASH",
        "str",
        '""',
        "payments",
        "Flutterwave webhook verif-hash header value.",
    ),
    # Communication providers
    SettingSpec(
        "WHATSAPP_API_TOKEN",
        "str",
        '""',
        "communication",
        "WhatsApp Cloud API access token.",
    ),
    SettingSpec(
        "WHATSAPP_API_URL",
        "str",
        '""',
        "communication",
        "WhatsApp Cloud API base URL.",
    ),
    SettingSpec(
        "WHATSAPP_BUSINESS_NUMBER",
        "str",
        '""',
        "communication",
        "Sender business phone number (E.164).",
    ),
    SettingSpec(
        "WHATSAPP_VERIFY_TOKEN",
        "str",
        '""',
        "communication",
        "Verify token returned during the WhatsApp webhook GET handshake.",
    ),
    SettingSpec(
        "WHATSAPP_APP_SECRET",
        "str",
        '""',
        "communication",
        "Meta App Secret used to verify X-Hub-Signature-256 on POST deliveries.",
    ),
    SettingSpec(
        "ZOOM_API_KEY",
        "str",
        '""',
        "communication",
        "Zoom JWT app API key.",
    ),
    SettingSpec(
        "ZOOM_API_SECRET",
        "str",
        '""',
        "communication",
        "Zoom JWT app API secret.",
    ),
    SettingSpec(
        "ZOOM_WEBHOOK_SECRET_TOKEN",
        "str",
        '""',
        "communication",
        "Zoom webhook secret token used for v0= signature validation.",
    ),
    # Marketing
    SettingSpec(
        "MARKETING_DEMO_WEBHOOK_URL",
        "str",
        '""',
        "marketing",
        "Optional webhook the demo form posts to.",
    ),
    SettingSpec(
        "MARKETING_CONTACT_WEBHOOK_URL",
        "str",
        '""',
        "marketing",
        "Optional webhook the contact form posts to (falls back to demo).",
    ),
    SettingSpec(
        "MARKETING_ANALYTICS_ENABLED",
        "bool",
        "False",
        "marketing",
        "Enable client-side marketing analytics beacon.",
    ),
    SettingSpec(
        "MARKETING_ANALYTICS_ENDPOINT",
        "str",
        '""',
        "marketing",
        "Endpoint the marketing analytics beacon posts to.",
    ),
    # Analytics warehouse export
    SettingSpec(
        "ANALYTICS_WAREHOUSE_URL",
        "str",
        '""',
        "ops",
        "Daily warehouse export endpoint (no-op when unset).",
    ),
    SettingSpec(
        "ANALYTICS_WAREHOUSE_API_KEY",
        "str",
        '""',
        "ops",
        "Bearer token for the warehouse endpoint.",
    ),
    # Audit / HMAC
    SettingSpec(
        "AUDIT_HMAC_DUAL_SIGN_WINDOW_DAYS",
        "int",
        "30",
        "security",
        "Days the rotated audit HMAC key remains accepted (dual-sign window).",
    ),
    SettingSpec(
        "NON_REPUDIATION_SIGNING_KEY",
        "str",
        '""',
        "security",
        "Optional dedicated HMAC key for non-repudiation records; falls back to SECRET_KEY.",
    ),

    # ---- AI / LLM ------------------------------------------------------------
    SettingSpec("AI_ALLOW_RULES_FALLBACK", "bool", "True", "ai", "Fallback to deterministic rules when AI provider is unreachable."),
    SettingSpec("AI_COPILOT_ENABLED", "bool", "False", "ai", "Master switch for the in-product AI copilot surface."),
    SettingSpec("AI_EMBEDDING_OLLAMA_MODEL", "str", '"all-minilm"', "ai", "Ollama embedding model name."),
    SettingSpec("TENANT_RAG_BUNDLE_SIGNING_KEY", "str", '""', "security", "HMAC key for signed tenant RAG bundle export/import."),
    SettingSpec("AI_GATEWAY_ENABLED", "bool", "True", "ai", "Master switch for the AI gateway abstraction."),
    SettingSpec("LITELLM_LASTGOOD_GRACE_SECONDS", "str", '""', "ai", "Grace period for retaining the last healthy LiteLLM probe result; runtime clamps 60-3600 seconds."),
    SettingSpec("AI_PROVIDER_PREFERENCE", "tuple[str]", "()", "ai", "Ordered list of AI providers to try (anthropic, openai, ollama, …)."),
    SettingSpec("AI_PROVIDER_TIMEOUT_SECONDS", "int", "30", "ai", "Per-provider request timeout."),
    SettingSpec("OLLAMA_CLI_PATH", "str", '"ollama"', "ai", "Path to the local Ollama CLI binary."),
    SettingSpec("OLLAMA_ENDPOINT", "str", '"http://localhost:11434"', "ai", "Ollama HTTP endpoint."),
    SettingSpec("OLLAMA_MODEL", "str", '"llama3"', "ai", "Default Ollama model."),
    SettingSpec("OLLAMA_PULL_TIMEOUT_SECONDS", "int", "600", "ai", "Timeout for `ollama pull` operations."),
    SettingSpec("OPEN_WEBUI_URL", "str", '""', "ai", "Optional Open WebUI URL surfaced to operators."),

    # ---- Tenancy / multi-region ---------------------------------------------
    SettingSpec("ALLOW_LEGACY_SINGLE_TENANT_REDIRECTS", "bool", "False", "tenancy", "Permit legacy single-tenant redirects (set False for new deployments)."),
    SettingSpec("MULTI_TENANT_BASE_DOMAIN", "str", '""', "tenancy", "Base apex domain for tenant subdomains."),
    SettingSpec("USE_DJANGO_TENANTS", "bool", "False", "tenancy", "Switch between schema-per-tenant (django-tenants) and shared-DB modes."),
    SettingSpec("TENANCY_MODE", "str", '"shared"', "tenancy", "High-level tenancy mode (shared / schema / db)."),
    SettingSpec("DB_POOL_MODE", "str", '"direct"', "tenancy", "Database endpoint mode: direct, session, or transaction. Transaction is not currently supported."),
    SettingSpec("SINGLE_TENANT", "bool", "False", "tenancy", "Force single-tenant operation (disables host-based dispatch)."),
    SettingSpec("SHARED_APPS", "tuple[str]", "()", "tenancy", "django-tenants SHARED_APPS list."),
    SettingSpec("TENANT_APPS", "tuple[str]", "()", "tenancy", "django-tenants TENANT_APPS list."),
    SettingSpec("TENANT_EXAMPLE_SLUG", "str", '""', "tenancy", "Example tenant slug used in demos / docs."),
    SettingSpec("ENABLE_MULTI_REGION", "bool", "False", "tenancy", "Enable multi-region routing primitives."),
    SettingSpec("REGION_CODE", "str", '""', "tenancy", "ISO region code for the current deployment."),
    SettingSpec("PLATFORM_DEFAULT_REGION_CODE", "str", '""', "tenancy", "Fallback region when a tenant has none set."),
    SettingSpec("DATABASE_READ_REPLICA_ALIAS", "str", '"default"', "tenancy", "Django DB alias for the read replica."),
    SettingSpec("RUNTIME_TENANT_CACHE_TTL", "int", "60", "tenancy", "Seconds to cache tenant runtime resolution."),

    # ---- API / rate limiting ------------------------------------------------
    SettingSpec("API_TENANT_MAX_REQUESTS_PER_MINUTE", "int", "600", "ops", "Per-tenant API rate ceiling (TenantApiQuotaMiddleware)."),
    SettingSpec("DISABLE_TENANT_API_QUOTA", "bool", "False", "ops", "Bypass TenantApiQuotaMiddleware for debugging."),
    SettingSpec("GLOBAL_HOT_PATH_RATE_LIMIT_RPM", "int", "60", "security", "Per-IP cap on OneRoster/SCIM/LTI/token hot paths."),

    # ---- App / build version + endpoints ------------------------------------
    SettingSpec("APP_VERSION", "str", '""', "ops", "Human-readable app version surfaced at /-/version/."),
    SettingSpec("BASE_URL", "str", '""', "ops", "Public base URL for absolute-link generation."),
    SettingSpec("SITE_URL", "str", '""', "ops", "Synonym for BASE_URL used in older code paths."),
    SettingSpec("SITE_NAME", "str", '"RunMyCampus"', "ops", "Public site name used in metadata + emails."),
    SettingSpec("SITE_SETTINGS", "dict", "{}", "ops", "Generic site-level config bag (legacy)."),
    SettingSpec("CELERY_BROKER_URL", "str", '""', "ops", "Celery broker URL (Redis / RabbitMQ); empty makes tasks run inline (eager) so broker-less deploys still execute deferred work."),
    SettingSpec("RMC_DISABLE_EAGER_FALLBACK", "bool", "False", "ops", "When CELERY_BROKER_URL is empty, set 1 to keep tasks PENDING for a later worker instead of running them inline."),
    SettingSpec("OBSERVABILITY_API_KEY", "str", '""', "ops", "Optional API key for the observability ingestion endpoint."),
    SettingSpec("RUM_INGEST_KEY", "str", '""', "ops", "Real User Monitoring beacon ingest key."),
    SettingSpec("RMC_LAYOUT_OBSERVABILITY_ENABLED", "bool", "True", "ops", "Master kill switch for bounded browser layout observation."),
    SettingSpec("INTELLIGENCE_PROMOTION_SIGNING_KEY", "str", '""', "security", "Secret used to sign reviewed intelligence-promotion evidence envelopes."),
    SettingSpec("BROWSER_AI_ENABLED", "bool", "False", "ai", "Enable operator-staged, same-origin browser inference."),
    SettingSpec("BROWSER_AI_MANIFEST_PATH", "str", '""', "ai", "Path to the checksum-pinned browser model pack manifest."),
    SettingSpec("BROWSER_AI_MIN_DEVICE_MEMORY_GB", "int", "4", "ai", "Minimum reported client memory for browser inference."),
    SettingSpec("BROWSER_AI_MIN_FREE_BYTES", "int", "536870912", "ai", "Minimum estimated free client storage for browser inference."),
    SettingSpec("LOCAL_VOICE_ENABLED", "bool", "False", "ai", "Enable explicit-consent local/LAN speech accessibility."),
    SettingSpec("LOCAL_VOICE_STT_ENDPOINT", "str", '""', "ai", "Operator-configured local speech-to-text endpoint."),
    SettingSpec("LOCAL_VOICE_TTS_ENDPOINT", "str", '""', "ai", "Operator-configured local text-to-speech endpoint."),
    SettingSpec("LOCAL_VOICE_ALLOWED_HOSTS", "list[str]", "[]", "security", "Exact endpoint hosts allowed for local voice calls."),
    SettingSpec("LOCAL_VOICE_LANGUAGES", "list[str]", '["en"]', "ai", "Languages certified by the operator for local voice."),
    SettingSpec("LOCAL_VOICE_TIMEOUT_SECONDS", "float", "20.0", "ai", "Timeout for local voice endpoint calls."),
    SettingSpec("LOCAL_VOICE_MAX_AUDIO_BYTES", "int", "2000000", "security", "Maximum accepted local voice recording size."),
    SettingSpec("LOCAL_VOICE_MAX_TRANSCRIPT_CHARS", "int", "4000", "security", "Maximum local voice transcript length."),
    SettingSpec("LOCAL_VOICE_MAX_TTS_CHARS", "int", "2000", "security", "Maximum local TTS input length."),
    SettingSpec("LOCAL_VOICE_MAX_TTS_BYTES", "int", "4000000", "security", "Maximum local TTS response size."),
    SettingSpec("LOCAL_VOICE_RATE_LIMIT_PER_MINUTE", "int", "10", "security", "Per-tenant/user local voice request limit."),
    SettingSpec("OPENSEARCH_DSN", "str", '""', "ops", "OpenSearch / Elasticsearch DSN for log shipping."),
    SettingSpec("RUNNING_TESTS", "bool", "False", "ops", "Set automatically when pytest / Django test runner is active."),
    SettingSpec("WEASYPRINT_BASEURL", "str", '""', "ops", "Base URL passed to WeasyPrint for relative asset resolution."),

    # ---- Compliance / audit -------------------------------------------------
    SettingSpec("COMPLIANCE_ALERTS", "dict", "{}", "compliance", "Alert routing config for compliance violations."),
    SettingSpec("COMPLIANCE_DASHBOARD_CACHE_SECONDS", "int", "300", "compliance", "Compliance dashboard cache TTL."),
    SettingSpec("COMPLIANCE_EXPORT_MAX_ROWS", "int", "100000", "compliance", "Cap on rows per compliance export."),
    SettingSpec("COMPLIANCE_ACCESS_LOG_GET_SAMPLE_RATE", "float", "0.25", "compliance", "Sampling rate for successful safe-method access logs; mutations and errors always log."),
    SettingSpec("DATA_RETENTION", "dict", "{}", "compliance", "Per-model retention overrides (days)."),
    SettingSpec("AUDIT_ARCHIVE_ROOT", "str", '""', "compliance", "Filesystem root for signed compliance retention archives."),
    SettingSpec("AUDIT_ARCHIVE_SIGNING_KEY", "str", '""', "security", "Dedicated HMAC key for compliance retention archives."),
    SettingSpec("AUDIT_RETENTION_APPROVAL_TOKEN", "str", '""', "security", "Explicit approval token required to purge verified compliance archives."),
    SettingSpec("INCIDENT_RESPONSE", "dict", "{}", "compliance", "Incident-response runbook routing config."),
    SettingSpec("THREAT_DETECTION", "dict", "{}", "compliance", "Thresholds for the periodic threat-detection job."),
    SettingSpec("ENABLE_IP_COUNTRY_ACCESS_CONTROL", "bool", "False", "compliance", "Enforce country-of-origin restrictions on access."),
    SettingSpec("BYPASS_ACCESS_CONTROL_FOR_SUPERUSERS", "bool", "False", "security", "Allow superusers through tenant access-control gates (debug only)."),
    SettingSpec("ENTERPRISE_SUPER_HTTP_AUDIT", "bool", "False", "compliance", "Audit every super-host HTTP request (enterprise-only)."),

    # ---- Conversion lock + activation gate ----------------------------------
    SettingSpec("CONVERSION_LOCK_ALLOWED_PREFIXES", "tuple[str]", "()", "ops", "Path prefixes always allowed under conversion lock."),
    SettingSpec("CONVERSION_LOCK_ALL_SCHOOLS", "bool", "False", "ops", "Apply conversion lock to every tenant."),
    SettingSpec("CONVERSION_LOCK_STRICT", "bool", "False", "ops", "Deny rather than redirect when locked."),
    SettingSpec("CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS", "bool", "False", "ops", "Restrict locked surface to a narrow workflow set."),
    SettingSpec("CONVERSION_SINGLE_ACTION_ENFORCED", "bool", "False", "ops", "Enforce one primary CTA per locked page."),
    SettingSpec("DISABLE_SCHOOL_ACTIVATION_GATE", "bool", "False", "ops", "Bypass the school activation gate (debug only)."),
    SettingSpec("CLICK_MEASUREMENT_PHASE", "str", '""', "marketing", "Click-measurement instrumentation phase label."),

    # ---- Impersonation / accounts ------------------------------------------
    SettingSpec("IMPERSONATION_DEFAULT_READ_ONLY", "bool", "True", "security", "Default impersonation sessions to read-only."),
    SettingSpec("IMPERSONATION_READ_ONLY_BLOCKED_WRITE_PREFIXES", "tuple[str]", "()", "security", "Path prefixes blocked from writes under read-only impersonation."),
    SettingSpec("LOGIN_LOCKOUT_ENABLED", "bool", "True", "security", "Enable cache-backed account login lockout."),
    SettingSpec("LOGIN_LOCKOUT_THRESHOLD", "int", "5", "security", "Failed login attempts allowed before account lockout."),
    SettingSpec("LOGIN_LOCKOUT_COOLOFF_SECONDS", "int", "900", "security", "Duration of cache-backed account login lockout."),
    SettingSpec("TURNSTILE_SITE_KEY", "str", '""', "security", "Cloudflare Turnstile public site key; inert when either key is absent."),
    SettingSpec("TURNSTILE_SECRET_KEY", "str", '""', "security", "Cloudflare Turnstile verification secret."),
    SettingSpec("TURNSTILE_VERIFY_URL", "str", '"https://challenges.cloudflare.com/turnstile/v0/siteverify"', "security", "Cloudflare Turnstile server-side verification endpoint."),
    SettingSpec("LOGIN_POW_ENABLED", "bool", "True", "security", "Enable the self-hosted proof-of-work login challenge (default bot defense, no account/third party)."),
    SettingSpec("LOGIN_POW_BITS", "int", "18", "security", "Proof-of-work difficulty (leading zero bits) for the login challenge."),
    SettingSpec("LOGIN_POW_TTL_SECONDS", "int", "600", "security", "Validity window (seconds) for an issued proof-of-work challenge."),
    SettingSpec("LOGIN_HONEYPOT_FIELD", "str", '"company_url"', "security", "Name of the hidden honeypot field on the login form."),
    SettingSpec("LOGIN_FORM_TOKEN_TTL_SECONDS", "int", "7200", "security", "Validity window (seconds) for the signed login-form timing token."),
    SettingSpec("LOGIN_MIN_FORM_SECONDS", "float", "1.0", "security", "Reject login submissions faster than this many seconds (bot timing trap)."),
    SettingSpec("IMPERSONATION_REQUIRE_JUSTIFICATION", "bool", "True", "security", "Require a typed justification before starting impersonation."),
    SettingSpec("IMPERSONATION_TOKEN_MAX_AGE_SECONDS", "int", "1800", "security", "Maximum impersonation token age."),
    SettingSpec("JIT_IMPERSONATION_CONSENT_DAYS", "int", "30", "security", "How long tenant consent for JIT impersonation lasts."),
    SettingSpec("JIT_IMPERSONATION_REQUIRE_CONSENT", "bool", "True", "security", "Require explicit tenant consent for just-in-time impersonation."),
    SettingSpec("ROLE_SESSION_TIMEOUTS", "dict", "{}", "security", "Per-role session inactivity timeouts (seconds)."),
    SettingSpec("SESSION_SAVE_EVERY_REQUEST", "bool", "False", "security", "Re-save session on every request to extend sliding window."),
    SettingSpec("STUDIO_APPROVAL_HUB_TENANT_BASE_URL", "str", '""', "ops", "Approval hub URL used for cross-host workflow links."),

    # ---- WebAuthn / SSO -----------------------------------------------------
    SettingSpec("WEBAUTHN_RP_ID", "str", '""', "security", "WebAuthn Relying Party ID (typically your apex domain)."),
    SettingSpec("WEBAUTHN_RP_NAME", "str", '"RunMyCampus"', "security", "WebAuthn Relying Party display name."),
    SettingSpec("LTI_REQUIRE_SIGNED_ID_TOKEN", "bool", "True", "security", "Reject LTI launches without a signed id_token."),
    SettingSpec("ONEROSTER_WEBHOOK_SECRET", "str", '""', "security", "OneRoster webhook signing secret."),

    # ---- Manager host cookies / domains -------------------------------------
    SettingSpec("MANAGER_CSRF_COOKIE_DOMAIN", "str", '""', "security", "Optional cookie domain for the manager-host CSRF cookie."),
    SettingSpec("MANAGER_CSRF_COOKIE_NAME", "str", '"rmc_manager_csrftoken"', "security", "Name of the manager-host CSRF cookie (isolated from tenant cookies)."),
    SettingSpec("MANAGER_PLATFORM_BASE_URL", "str", '""', "ops", "Public base URL of the manager / control plane."),
    SettingSpec("MANAGER_SESSION_COOKIE_DOMAIN", "str", '""', "security", "Optional cookie domain for the manager-host session cookie."),
    SettingSpec("MANAGER_SESSION_COOKIE_NAME", "str", '"rmc_manager_sessionid"', "security", "Name of the manager-host session cookie."),

    # ---- CSP (the security middleware exposes these overrides) --------------
    SettingSpec("CSP_ENFORCE", "bool", "True", "security", "Enforce Content-Security-Policy (default True since v2.57; override to False for Report-Only)."),
    SettingSpec("BANK_ACCOUNT_CHANGES_REQUIRE_DUAL_AUTH", "bool", "True", "security", "When True (default since v2.63), Django-admin edits to BankAccount route through the four-eyes dual-authorization flow (apps.finance.bank_account_dual_auth). A different administrator must approve before the live row is touched."),
    SettingSpec("BANK_ACCOUNT_CHANGE_REQUEST_TTL_HOURS", "int", "48", "security", "Lifetime of a PENDING BankAccountChangeRequest before it auto-expires (Celery beat sweeps via apps.finance.bank_account_dual_auth.expire_stale_requests)."),
    SettingSpec("CSP_REPORT_URI", "str", '"/security/csp-report/"', "security", "URI browsers POST CSP violation reports to."),
    SettingSpec("CSP_EXTRA_CONNECT_SRC", "tuple[str]", "()", "security", "Additional connect-src origins."),
    SettingSpec("CSP_EXTRA_FRAME_ANCESTORS", "tuple[str]", "()", "security", "Additional frame-ancestors entries."),
    SettingSpec("CSP_EXTRA_IMG_SRC", "tuple[str]", "()", "security", "Additional img-src origins."),
    SettingSpec("CSP_EXTRA_SCRIPT_SRC", "tuple[str]", "()", "security", "Additional script-src origins (vendor SDKs / analytics)."),
    SettingSpec("CSP_EXTRA_STYLE_SRC", "tuple[str]", "()", "security", "Additional style-src origins."),

    # ---- Marketing content + visuals ----------------------------------------
    SettingSpec("MARKETING_ANALYTICS_ENDPOINT_URL", "str", '""', "marketing", "Endpoint the marketing analytics beacon posts to (synonym for MARKETING_ANALYTICS_ENDPOINT)."),
    SettingSpec("MARKETING_ANALYTICS_SCRIPT_URL", "str", '""', "marketing", "External analytics script URL injected into the marketing shell when configured."),
    SettingSpec("MARKETING_BASE_SCHEME", "str", '"https"', "marketing", "URL scheme used when generating absolute marketing URLs."),
    SettingSpec("MARKETING_CALENDLY_URL", "str", '""', "marketing", "Calendly link surfaced on the demo page."),
    SettingSpec("MARKETING_COMPARISON_TABLE", "list", "[]", "marketing", "Server-driven competitor comparison table."),
    SettingSpec("MARKETING_CONTENT_REGION", "str", '""', "marketing", "Region key for content variant selection."),
    SettingSpec("MARKETING_CONTENT_VARIANT", "str", '""', "marketing", "Active marketing content variant (A/B test)."),
    SettingSpec("MARKETING_CONTROL_PLANE_DIAGRAM_URL", "str", '""', "marketing", "Asset URL for the control-plane diagram."),
    SettingSpec("MARKETING_DATA_INTELLIGENCE_LOOP_IMAGE_URL", "str", '""', "marketing", "Asset URL for the data-intelligence loop image."),
    SettingSpec("MARKETING_DEMO_TENANT_URL", "str", '""', "marketing", "Public demo tenant URL surfaced on the demo page."),
    SettingSpec("MARKETING_DEMO_WHAT_YOU_SEE", "list", "[]", "marketing", "Server-driven 'what you see in the demo' bullet list."),
    SettingSpec("MARKETING_ECOSYSTEM_DIAGRAM_URL", "str", '""', "marketing", "Asset URL for the ecosystem diagram."),
    SettingSpec("MARKETING_ECOSYSTEM_IMAGE_URL", "str", '""', "marketing", "Asset URL for the ecosystem hero image."),
    SettingSpec("MARKETING_ECOSYSTEM_MAP_IMAGE_URL", "str", '""', "marketing", "Asset URL for the ecosystem world-map image."),
    SettingSpec("MARKETING_GLOBAL_MAP_IMAGE_URL", "str", '""', "marketing", "Asset URL for the global-map image."),
    SettingSpec("MARKETING_GLOBAL_STATS", "list", "[]", "marketing", "Server-driven global-stats panel rows."),
    SettingSpec("MARKETING_HEALTH_SCORE_VISUAL_URL", "str", '""', "marketing", "Asset URL for the health-score visual."),
    SettingSpec("MARKETING_HERO_IMAGE_SIZES", "str", '""', "marketing", "<img sizes=...> string for the hero image."),
    SettingSpec("MARKETING_HERO_IMAGE_SRCSET", "str", '""', "marketing", "<img srcset=...> string for the hero image."),
    SettingSpec("MARKETING_HERO_IMAGE_URL", "str", '""', "marketing", "Marketing hero image URL."),
    SettingSpec("MARKETING_HERO_VARIANT_B_SUBLINE", "str", '""', "marketing", "Hero subline string for A/B variant B."),
    SettingSpec("MARKETING_HERO_VIDEO_POSTER_URL", "str", '""', "marketing", "Hero video poster image."),
    SettingSpec("MARKETING_HERO_VIDEO_URL", "str", '""', "marketing", "Hero video URL."),
    SettingSpec("MARKETING_ILLUSTRATION_GLOBE_URL", "str", '""', "marketing", "Globe illustration URL."),
    SettingSpec("MARKETING_ILLUSTRATION_STUDENTS_URL", "str", '""', "marketing", "Students illustration URL."),
    SettingSpec("MARKETING_ILLUSTRATION_WORKFLOW_URL", "str", '""', "marketing", "Workflow illustration URL."),
    SettingSpec("MARKETING_MARKETPLACE_IMAGE_URL", "str", '""', "marketing", "Marketplace illustration / hero image."),
    SettingSpec("MARKETING_MIGRATION_CLOUD_DIAGRAM_URL", "str", '""', "marketing", "Migration cloud diagram URL."),
    SettingSpec("MARKETING_MIGRATION_DIAGRAM_URL", "str", '""', "marketing", "Migration architecture diagram URL."),
    SettingSpec("MARKETING_MIGRATION_FLOW_IMAGE_URL", "str", '""', "marketing", "Migration flow image URL."),
    SettingSpec("MARKETING_MIGRATION_STUDIO_IMAGE_URL", "str", '""', "marketing", "Migration studio screenshot URL."),
    SettingSpec("MARKETING_NEWSLETTER_FORM_ACTION", "str", '""', "marketing", "Override action URL for the footer newsletter form."),
    SettingSpec("MARKETING_OUTCOME_METRICS", "list", "[]", "marketing", "Outcome metrics rendered on the proof page."),
    SettingSpec("MARKETING_PLATFORM_ARCHITECTURE_DIAGRAM_URL", "str", '""', "marketing", "Platform architecture diagram URL."),
    SettingSpec("MARKETING_PRODUCT_DEMO_IMAGE_URL", "str", '""', "marketing", "Product demo screenshot URL."),
    SettingSpec("MARKETING_PRODUCT_TOUR_URL", "str", '""', "marketing", "External product tour URL (e.g. Storylane)."),
    SettingSpec("MARKETING_PRODUCT_VISUALIZATION_SLIDES", "list", "[]", "marketing", "Server-driven product-visualization slides."),
    SettingSpec("MARKETING_PROOF_HERO_IMAGE_KEY", "str", '""', "marketing", "Lookup key for the proof-hero image variant."),
    SettingSpec("MARKETING_REPLACEMENT_MESSAGING", "dict", "{}", "marketing", "Server-driven 'why replace X' messaging map."),
    SettingSpec("MARKETING_ROLE_PREVIEW_IMAGES", "dict", "{}", "marketing", "Per-role preview image URLs."),
    SettingSpec("MARKETING_SCHOOL_IN_A_BOX_FLOW_IMAGE_URL", "str", '""', "marketing", "School-in-a-box flow image URL."),
    SettingSpec("MARKETING_SETUP_STUDIO_FLOW_IMAGE_URL", "str", '""', "marketing", "Setup studio flow image URL."),
    SettingSpec("MARKETING_SETUP_STUDIO_IMAGE_URL", "str", '""', "marketing", "Setup studio screenshot URL."),
    SettingSpec("MARKETING_STATUS_PAGE_URL", "str", '""', "marketing", "External status-page URL referenced from /trust/."),
    SettingSpec("MARKETING_VIDEO_TESTIMONIALS", "list", "[]", "marketing", "Server-driven testimonial video list."),

    # ---- Marketplace + finance ---------------------------------------------
    SettingSpec("MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING", "bool", "True", "marketplace", "Block paid app installs without an active billing account."),
    SettingSpec("MARKETPLACE_PLATFORM_FEE_PERCENT", "Decimal", "10", "marketplace", "Platform fee percentage on marketplace installs."),
    SettingSpec("DEFAULT_CURRENCY", "str", '"USD"', "finance", "Default currency code when tenant has none set."),
    SettingSpec("PLATFORM_DEFAULT_CURRENCY", "str", '"USD"', "finance", "Platform-wide default currency."),
    SettingSpec("EXCHANGE_RATES", "dict", "{}", "finance", "Static FX rate overrides (test / fallback)."),
    SettingSpec(
        "REQUEST_TIMEOUT_SECONDS",
        "int",
        "120",
        "ops",
        "Wall-clock cap on synchronous HTTP requests (0 disables RequestTimeoutMiddleware).",
    ),
    SettingSpec("DEFAULT_SCHOOL_TIMEZONE", "str", '"UTC"', "ops", "Default timezone applied to new schools."),
    SettingSpec("PLATFORM_DEFAULT_TIMEZONE", "str", '"UTC"', "ops", "Platform-wide default timezone."),
    SettingSpec("PLATFORM_DEFAULT_GRADING_SCALE", "str", '""', "academics", "Default grading scale slug for new schools."),

    # ---- Reports / OCR -----------------------------------------------------
    SettingSpec("MARKSHEET_OCR_COMMAND", "str", '""', "academics", "External OCR command line for marksheet ingestion."),
    SettingSpec("REPORT_SHARE_DAYS", "int", "30", "academics", "Days a shared-report link remains valid."),

    # ---- Comms providers ---------------------------------------------------
    SettingSpec("REGIONAL_FROM_EMAIL", "str", '""', "communication", "Per-region overridden DEFAULT_FROM_EMAIL."),
    SettingSpec(
        "EMAIL_SIGNING_REQUIRED",
        "bool",
        "False",
        "communication",
        (
            "Pillar 3 / Verified Communications: when True, "
            "AppConfig.ready raises EmailSigningMisconfigured if "
            "EMAIL_BACKEND is not a known DKIM-signing anymail provider. "
            "Opt-in for production; leave False in development."
        ),
    ),
    SettingSpec("SLACK_WEBHOOK_URL", "str", '""', "communication", "Slack incoming webhook for ops alerts."),
    SettingSpec("SMS_API_TOKEN", "str", '""', "communication", "Generic SMS provider API token."),
    SettingSpec("SMS_API_URL", "str", '""', "communication", "Generic SMS provider base URL."),
    SettingSpec("TWILIO_ACCOUNT_SID", "str", '""', "communication", "Twilio account SID."),
    SettingSpec("TWILIO_AUTH_TOKEN", "str", '""', "communication", "Twilio auth token."),
    SettingSpec("WHATSAPP_BASE_URL", "str", '""', "communication", "Optional override of the WhatsApp Cloud API base URL."),

    # ---- Support / help-desk -----------------------------------------------
    SettingSpec("SUPPORT_AI_AUTO_TRIAGE_ON_CREATE", "bool", "False", "ops", "Run AI triage on every new support ticket."),
    SettingSpec("SUPPORT_AI_KB_CONTEXT", "dict", "{}", "ops", "AI KB context map for support triage."),
    SettingSpec("AI_ENGINE_ROOM_SUPPORT", "bool", "True", "ai", "RAG-first first-line support via services.ai.gateway."),
    SettingSpec("AI_ENGINE_ROOM_TIMEOUT_SECONDS", "int", "15", "ai", "Ollama latency cap for engine-room support calls."),
    SettingSpec("AI_ENGINE_ROOM_MAX_INPUT_TOKENS", "int", "6000", "ai", "Max estimated input tokens for engine-room prompts."),
    SettingSpec("SUPPORT_SLA_RESOLUTION_HOURS", "int", "48", "ops", "SLA resolution target in hours."),
    SettingSpec("SUPPORT_SLA_RESPONSE_HOURS", "int", "8", "ops", "SLA first-response target in hours."),
    SettingSpec("SUPPORT_TICKET_INAPP_FANOUT_OPERATORS", "tuple[str]", "()", "ops", "Operator usernames receiving in-app ticket notifications."),
    SettingSpec("SUPPORT_TICKET_NOTIFY_EMAIL", "bool", "True", "ops", "Email operators on new ticket events."),
    SettingSpec("SUPPORT_TICKET_NOTIFY_INAPP", "bool", "True", "ops", "Push in-app notifications on new ticket events."),
    SettingSpec("SUPPORT_TICKET_NOTIFY_SUBMITTER_ON_VISIBLE_REPLY", "bool", "True", "ops", "Notify submitter when an operator posts a visible reply."),
    SettingSpec("SUPPORT_TICKET_PUSH_OPERATORS_ON_CREATE", "bool", "True", "ops", "Push notify operators on ticket create."),
    SettingSpec("SUPPORT_TICKET_PUSH_SUBMITTER_ON_VISIBLE_REPLY", "bool", "True", "ops", "Push notify submitter on visible reply."),
    SettingSpec("SUPPORT_TICKET_WEBHOOK_SECRET", "str", '""', "ops", "Signing secret for outbound ticket webhooks."),
    SettingSpec("SUPPORT_TICKET_WEBHOOK_URL", "str", '""', "ops", "URL to POST ticket events to (Slack / PagerDuty / etc.)."),

    # ---- Sync / SLOs -------------------------------------------------------
    SettingSpec("SYNC_CONFLICT_PENDING_SLO_MAX", "int", "100", "ops", "Cap on pending sync conflicts before alerting."),
    SettingSpec("RMC_SYNC_SODP_CONFLICT_MAX", "int", "25", "ops", "SODP OfflineAction conflict backlog cap before the sync_backlog_monitor opens a platform incident."),
    SettingSpec("RMC_SYNC_WAL_DEADLETTER_MAX", "int", "10", "ops", "WAL dead-letter total depth cap before the sync_backlog_monitor opens a platform incident."),
    SettingSpec("WEBHOOK_P95_LATENCY_SLO_MS", "int", "1500", "ops", "Webhook delivery p95 latency SLO."),
    SettingSpec("WEBHOOK_SUCCESS_SLO_PERCENT", "float", "99.0", "ops", "Webhook delivery success-rate SLO percent."),

    # ---- Tenant lifecycle --------------------------------------------------
    SettingSpec("TENANT_LIFECYCLE_CHURN_INACTIVITY_DAYS", "int", "30", "ops", "Days of inactivity before the churn signal fires."),
    SettingSpec("TENANT_LIFECYCLE_CHURN_PAYMENT_FAILED_DAYS", "int", "7", "ops", "Days after payment failure before churn signal fires."),
    SettingSpec("TENANT_LIFECYCLE_FIRST_ACTION_STALL_DAYS", "int", "7", "ops", "Days a fresh tenant can stall before nudge."),
    SettingSpec("TENANT_LIFECYCLE_ONBOARDING_STALL_DAYS", "int", "14", "ops", "Days an onboarding tenant can stall before escalation."),

    # ---- Identity / session security --------------------------------------
    SettingSpec(
        "SESSION_PINNING_ENABLED",
        "bool",
        "True",
        "security",
        "Bind authenticated sessions to the (IP, User-Agent hash) captured at first sight; "
        "flush + CRITICAL audit if a later request from the same session presents a different pair. "
        "See apps.accounts.middleware_session_pinning.SessionPinningMiddleware.",
    ),
    SettingSpec(
        "PASSKEY_ONLY_ROLES",
        "tuple[str]",
        "()",
        "security",
        "Role tokens (matched against User.role, case-insensitive) that are forbidden from "
        "password-form login. Members of these roles must sign in via WebAuthn passkey. "
        "Enforced in apps.accounts.views.login_view.",
    ),

    # ---- Misc / runbooks ---------------------------------------------------
    SettingSpec("CONTROL_PLANE_RUNBOOKS_URL", "str", '""', "ops", "Public URL where ops runbooks live."),
    SettingSpec("FIFTY_PCT_REDUCTION_CLAIM_ALLOWED", "bool", "False", "marketing", "Honesty gate — only show '50% reduction' claim with proof."),
    SettingSpec("RUNMYCAMPUS_DEMO_ENABLED", "bool", "False", "marketing", "Enable in-product demo flows."),
    SettingSpec("RUNMYCAMPUS_DEMO_MODE", "str", '""', "marketing", "Demo mode label (sandbox / staging / live)."),
    SettingSpec("TESTING_MATRIX_REGIONS", "tuple[str]", "()", "ops", "Regions exercised by the multi-region test matrix."),
    SettingSpec("WEDGE_14_22_OPERATOR_PLAYBOOK_URL", "str", '""', "ops", "Operator playbook URL for the 14-22 wedge program."),

    # ---- Wave 1261 — registry strict closure (2026-05-17) ----------------
    SettingSpec("AI_HEALTH_CACHE_TTL_SECONDS", "int", "60", "ai", "TTL for cached /api/ai/health/ responses."),
    SettingSpec("ANYMAIL", "dict", "{}", "communication", "Anymail provider configuration dict."),
    SettingSpec("API_IDEMPOTENCY_TTL_SECONDS", "int", "86400", "api", "TTL for API idempotency keys."),
    SettingSpec("AT_RISK_MODEL_DIR", "str", '""', "ai", "Directory for at-risk ML model artifacts."),
    SettingSpec("AT_RISK_MODEL_PATH", "str", '""', "ai", "Path to at-risk ML model file."),
    SettingSpec("AWS_REGION", "str", '""', "infra", "Default AWS region for Route53/S3 helpers."),
    SettingSpec("AWS_ROUTE53_HOSTED_ZONE_ID", "str", '""', "infra", "Route53 hosted zone id for custom domains."),
    SettingSpec("AWS_ROUTE53_REGION", "str", '""', "infra", "Route53 API region override."),
    SettingSpec("CELERY_BEAT_SCHEDULE", "dict", "{}", "ops", "Celery beat schedule dict."),
    SettingSpec("CLOUDFLARE_API_TOKEN", "str", '""', "infra", "Cloudflare API token for DNS automation."),
    SettingSpec("CLOUDFLARE_PROXIED", "bool", "True", "infra", "Whether Cloudflare records are proxied."),
    SettingSpec("CLOUDFLARE_ZONE_ID", "str", '""', "infra", "Cloudflare zone id for apex domain."),
    SettingSpec("CORS_ALLOWED_ORIGINS", "list[str]", "[]", "security", "Extra CORS origins beyond defaults."),
    SettingSpec("DATA_RESIDENCY_ENFORCE", "bool", "False", "compliance", "Enforce data residency routing rules."),
    SettingSpec("DATA_RESIDENCY_STRICT_UNKNOWN", "bool", "None (unset follows DATA_RESIDENCY_ENFORCE)", "compliance", "Unknown source/target region under enforcement: unset fails CLOSED whenever DATA_RESIDENCY_ENFORCE is on; 0 is an explicit opt-out; 1 forces strict even in audit-only posture."),
    SettingSpec("DATA_RESIDENCY_DEFAULT_STORE_REGION", "str", '"global"', "compliance", "Declared region of the default DB; unresolvable-alias ops are adjudicated against it under enforcement."),
    SettingSpec("DATA_RESIDENCY_REPLICA_ALIASES", "dict", "{}", "compliance", "DB alias map for residency replicas."),
    SettingSpec("DEFAULT_ADMIN_PAGE_SIZE", "int", "25", "ui", "Default admin changelist page size."),
    SettingSpec("DEFAULT_AUDIT_PAGE_SIZE", "int", "50", "ui", "Default audit log page size."),
    SettingSpec("DEFAULT_PAGE_SIZE", "int", "25", "ui", "Default list pagination size."),
    SettingSpec("DEFAULT_WIDGET_PAGE_SIZE", "int", "10", "ui", "Default dashboard widget page size."),
    SettingSpec("DISCORD_WEBHOOK_URL", "str", '""', "ops", "Discord webhook for ops alerts."),
    SettingSpec("DNS_PROVIDER", "str", '""', "infra", "DNS automation provider key (route53/cloudflare)."),
    SettingSpec("EMAIL_BACKEND_FALLBACK", "str", '""', "communication", "Fallback email backend import path."),
    SettingSpec("GRADE_PREDICTION_MODEL_PATH", "str", '""', "ai", "Grade prediction model artifact path."),
    SettingSpec("GRADE_WEIGHT_EXAM", "float", "0.0", "academics", "Default exam weight for grade calculations."),
    SettingSpec("GRADE_WEIGHT_MOCK", "float", "0.0", "academics", "Default mock exam weight."),
    SettingSpec("GRADE_WEIGHT_PRACTICAL", "float", "0.0", "academics", "Default practical weight."),
    SettingSpec("GRADE_WEIGHT_SEQ1", "float", "0.0", "academics", "Default sequence-1 weight."),
    SettingSpec("GRADE_WEIGHT_SEQ2", "float", "0.0", "academics", "Default sequence-2 weight."),
    SettingSpec("IMPORT_MAX_ROWS", "int", "5000", "ops", "Max rows per bulk import job."),
    SettingSpec("LANGUAGE_COOKIE_AGE", "int", "31536000", "i18n", "Language preference cookie max-age."),
    SettingSpec("LANGUAGE_COOKIE_DOMAIN", "str", '""', "i18n", "Language cookie domain override."),
    SettingSpec("LANGUAGE_COOKIE_HTTPONLY", "bool", "False", "i18n", "Language cookie HttpOnly flag."),
    SettingSpec("LANGUAGE_COOKIE_NAME", "str", '"django_language"', "i18n", "Language cookie name."),
    SettingSpec("LANGUAGE_COOKIE_PATH", "str", '"/"', "i18n", "Language cookie path."),
    SettingSpec("LANGUAGE_COOKIE_SAMESITE", "str", '"Lax"', "i18n", "Language cookie SameSite policy."),
    SettingSpec("LANGUAGE_COOKIE_SECURE", "bool", "False", "i18n", "Language cookie Secure flag."),
    SettingSpec("MARKETING_VERB_NAV_ENABLED", "bool", "False", "marketing", "Enable marketing verb-canonical nav (default: enterprise Platform/Solutions IA)."),
    SettingSpec("OAUTH_CALLBACK_BASE_URL", "str", '""', "security", "Base URL for OAuth callback construction."),
    SettingSpec("PASS_THRESHOLD_DEFAULT", "float", "10.0", "academics", "Default pass mark threshold."),
    SettingSpec("PAYMENT_MAX_AMOUNT", "int", "0", "finance", "Optional cap on payment amounts (0=disabled)."),
    SettingSpec("PGVECTOR_ENABLED", "bool", "False", "ai", "Enable pgvector-backed embeddings when available."),
    SettingSpec("PLATFORM_PALETTE_ACCENT", "str", '""', "branding", "Platform palette accent token."),
    SettingSpec("PLATFORM_PALETTE_BORDER_LIGHT", "str", '""', "branding", "Platform palette border-light token."),
    SettingSpec("PLATFORM_PALETTE_DANGER", "str", '""', "branding", "Platform palette danger token."),
    SettingSpec("PLATFORM_PALETTE_DASHBOARD_BG", "str", '""', "branding", "Platform palette dashboard background."),
    SettingSpec("PLATFORM_PALETTE_HERO_BG", "str", '""', "branding", "Platform palette hero background."),
    SettingSpec("PLATFORM_PALETTE_MUTED_SWATCH", "str", '""', "branding", "Platform palette muted swatch."),
    SettingSpec("PLATFORM_PALETTE_PRIMARY", "str", '""', "branding", "Platform palette primary token."),
    SettingSpec("PLATFORM_PALETTE_SUCCESS", "str", '""', "branding", "Platform palette success token."),
    SettingSpec("PLATFORM_PALETTE_SURFACE", "str", '""', "branding", "Platform palette surface token."),
    SettingSpec("PLATFORM_PALETTE_WARNING", "str", '""', "branding", "Platform palette warning token."),
    SettingSpec("PUBLIC_SITE_URL", "str", '""', "marketing", "Canonical public site URL for links."),
    SettingSpec("SLACK_BOT_TOKEN", "str", '""', "ops", "Slack bot token for notifications."),
    SettingSpec("SLACK_DEFAULT_CHANNEL", "str", '""', "ops", "Default Slack channel id/name."),
    SettingSpec("TEAMS_ACCESS_TOKEN", "str", '""', "ops", "Microsoft Teams access token."),
    SettingSpec("TEAMS_DEFAULT_CHAT_ID", "str", '""', "ops", "Default Teams chat id for alerts."),
    # Infrastructure / storage / brokers
    SettingSpec("AWS_STORAGE_BUCKET_NAME", "str", '""', "ops", "S3 bucket name when the S3 media/static backend is active."),
    SettingSpec("MEDIA_STORAGE_BACKEND", "str", '""', "ops", "Media storage backend: empty=local filesystem; s3/minio/r2=S3-compatible object store (also auto-on when AWS_S3_ENDPOINT_URL + AWS_STORAGE_BUCKET_NAME set)."),
    SettingSpec("AWS_S3_ENDPOINT_URL", "str", '""', "ops", "S3-compatible endpoint URL (set for MinIO / Cloudflare R2 / Backblaze B2; empty = real AWS S3)."),
    SettingSpec("AWS_ACCESS_KEY_ID", "str", '""', "ops", "Access key for the S3-compatible media store."),
    SettingSpec("AWS_SECRET_ACCESS_KEY", "str", '""', "ops", "Secret key for the S3-compatible media store."),
    SettingSpec("AWS_S3_REGION_NAME", "str", '""', "ops", "Region for the S3-compatible media store (e.g. auto for R2, us-east-1 for AWS)."),
    SettingSpec("AWS_S3_ADDRESSING_STYLE", "str", '"path"', "ops", "S3 addressing style; 'path' for MinIO, 'virtual' acceptable for AWS/R2."),
    SettingSpec("AWS_QUERYSTRING_AUTH", "bool", "True", "ops", "Sign media URLs (private buckets). Set 0 for public-read CDN delivery."),
    SettingSpec("AWS_DEFAULT_ACL", "str", '""', "ops", "Object ACL applied on upload (empty = bucket default; e.g. public-read for CDN)."),
    SettingSpec("BROKER_URL", "str", '""', "ops", "Celery broker URL (Redis/RabbitMQ)."),
    SettingSpec("KAFKA_BOOTSTRAP_SERVERS", "str", '""', "ops", "Kafka bootstrap servers for optional event streaming."),
    SettingSpec("EMAIL_TIMEOUT", "int", "10", "ops", "SMTP socket timeout in seconds."),
    SettingSpec("MANAGER_URLCONF", "str", '"config.manager_urls"', "ops", "URLconf module served on the manager host."),
    # Security / crypto
    SettingSpec("DJANGO_CRYPTOGRAPHY_KEYS", "list", "[]", "security", "MultiFernet key ring (newest-first) for encrypted model fields."),
    SettingSpec("DJANGO_CRYPTOGRAPHY_KEYS_SOURCE", "str", '"env"', "security", "Field-encryption key source: 'env' (default) or 'vault' (SH-6 opt-in)."),
    SettingSpec("DJANGO_CRYPTOGRAPHY_VAULT_MOUNT", "str", '"secret"', "security", "Vault KV v2 mount for the field-encryption key ring (when source=vault)."),
    SettingSpec("DJANGO_CRYPTOGRAPHY_VAULT_PATH", "str", '""', "security", "Vault KV v2 secret path holding the key ring (required when source=vault)."),
    SettingSpec("DJANGO_CRYPTOGRAPHY_VAULT_FIELD", "str", '"keys"', "security", "Field within the Vault secret holding the newest-first key ring."),
    SettingSpec("DJANGO_CRYPTOGRAPHY_VAULT_DRY_RUN", "bool", "False", "security", "Skip the Vault network call and fall back to env keys (CI/dev)."),
    SettingSpec("DJANGO_CRYPTOGRAPHY_VAULT_CACHE_SECONDS", "int", "300", "security", "Process cache TTL for the Vault-sourced key ring."),
    SettingSpec("GRAPHQL_INTROSPECTION_ENABLED", "bool", "False", "security", "Allow GraphQL schema introspection (kept off in prod)."),
    # Help center / KB ops
    SettingSpec("HELP_NORTH_STAR_WEEKLY_EMAIL", "bool", "False", "ops", "Send the weekly help-center north-star metrics email."),
    SettingSpec("HELP_ZERO_RESULT_AUTO_DRAFT_KB", "bool", "False", "ops", "Auto-draft a KB article when a help search returns zero results."),
    SettingSpec("KB_EMBEDDING_AUTO_REFRESH", "bool", "False", "ops", "Refresh KB embeddings automatically when articles change."),
    SettingSpec("KB_PGVECTOR_ENABLED", "bool", "False", "ops", "Use pgvector for KB semantic search when available."),
    # Cockpit / enrollment ops
    SettingSpec("COCKPIT_100X_RENDER_PREVIEW_DEMO", "bool", "False", "ux", "Enable the cockpit 100x render-preview demo surface."),
    SettingSpec("COCKPIT_200X_RENDER_PREVIEW_DEMO", "bool", "False", "ux", "Enable the cockpit 200x render-preview demo surface."),
    SettingSpec("ENROLLMENT_PEAK_MODE", "bool", "False", "ops", "Toggle enrollment peak-load handling behavior."),
    # Marketing surface
    SettingSpec("MARKETING_GEO_COUNTRY_OVERRIDE", "str", '""', "marketing", "Force the marketing geo to a country code (testing/preview)."),
    SettingSpec("MARKETING_INTENT_HOMEPAGE", "str", '""', "marketing", "Override the marketing homepage intent variant."),
    SettingSpec("MARKETING_KB_TENANT_SLUG", "str", '""', "marketing", "Tenant slug whose KB powers the public marketing help center."),
    SettingSpec("MARKETING_SCALE_COUNTRY_COUNT", "int", "0", "marketing", "Illustrative country count shown on marketing scale claims."),
    SettingSpec("MARKETING_SCALE_SCHOOL_COUNT", "int", "0", "marketing", "Illustrative school count shown on marketing scale claims."),
    SettingSpec("MARKETING_SCALE_ILLUSTRATIVE", "bool", "True", "marketing", "Whether marketing scale numbers are flagged illustrative."),
    # Compliance / MAA
    SettingSpec("MAA_TEXT_DRAFT_VERSIONS", "set", '{"v2.0"}', "compliance", "MAA versions still in draft (signature attempts are refused)."),
    # Migration Cloud audit + retention
    SettingSpec("MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR", "int", "1000", "ops", "Rate cap for migration-cloud audit events per tenant per hour."),
    SettingSpec("MIGRATION_CLOUD_AUDIT_OPS_EMAIL", "str", '""', "ops", "Operator email for migration-cloud audit alerts."),
    SettingSpec("MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED", "bool", "False", "ops", "Disable migration-cloud audit-event rate limiting."),
    SettingSpec("MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND", "str", '"local-env-key"', "security", "Backend selector for audit-event integrity signing."),
    SettingSpec("MIGRATION_CLOUD_AUDIT_ROOT_SIGNING_BACKEND", "str", '"local-env-key"', "security", "Backend for per-event root-key HMAC-SHA512 signing."),
    SettingSpec("MIGRATION_CLOUD_AUDIT_SIGNING_KEY", "str", '""', "security", "Key material for migration-cloud audit-event signing."),
    SettingSpec("MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN", "str", '""', "security", "Counsel approval token gating the audit retention purge command."),
    SettingSpec("MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN", "str", '""', "security", "Counsel approval token gating tenant data-retention purges."),
    SettingSpec("MIGRATION_CLOUD_EMIT_LEGACY_HEADERS", "bool", "True", "ops", "Emit legacy webhook headers during the 90-day migration window."),
    # Migration Cloud — guardian consent / intake / MAA / retention / smoke / throttle
    SettingSpec("MIGRATION_CLOUD_GUARDIAN_CONSENT_ACTIVE_VERSION", "str", '""', "compliance", "Active guardian-consent text version override for migration cloud."),
    SettingSpec("MIGRATION_CLOUD_GUARDIAN_CONSENT_REVOKE_WINDOW_DAYS", "int", "90", "compliance", "Days a guardian may revoke migration-cloud consent after grant."),
    SettingSpec("MIGRATION_CLOUD_INTAKE_FROM_EMAIL", "str", '""', "ops", "From-address for migration-cloud intake/consent emails (falls back to DEFAULT_FROM_EMAIL)."),
    SettingSpec("MIGRATION_CLOUD_LEGACY_HEADER_DEPRECATION_DATE", "str", '"2026-08-18"', "ops", "Date string advertised as the legacy webhook-header deprecation cutover."),
    SettingSpec("MIGRATION_CLOUD_MAA_DEFAULT_VERSION", "str", '"v1.0"', "compliance", "Default Migration Assistance Agreement version served to tenants."),
    SettingSpec("MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS", "list", "[]", "compliance", "Tenant IDs opted into the preview MAA version."),
    SettingSpec("MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL", "str", '""', "ops", "Operator alert email for migration-cloud nightly smoke and retention sweeps."),
    SettingSpec("MIGRATION_CLOUD_PUBLIC_HOSTNAME", "str", '""', "ops", "Public hostname used to build absolute migration-cloud consent links."),
    SettingSpec("MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS", "int", "180", "compliance", "Default retention window (days) for migration-cloud blobs."),
    SettingSpec("MIGRATION_CLOUD_RETENTION_MIN_DAYS", "int", "90", "compliance", "Minimum retention floor (days) for migration-cloud blobs."),
    SettingSpec("MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED", "bool", "False", "ops", "Kill-switch enabling the migration-cloud nightly synthetic smoke run."),
    SettingSpec("MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT", "str", '"smoke-test-tenant"', "ops", "Slug of the synthetic tenant used by the migration-cloud nightly smoke."),
    SettingSpec("MIGRATION_CLOUD_SSE_TRANSPORT", "str", '"wsgi-fallback"', "ops", "Transport mode for migration-cloud command-center SSE streams."),
    SettingSpec("MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_DISABLED", "bool", "False", "ops", "Disable the migration-cloud rate-limit saturation alert."),
    SettingSpec("MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_RATIO", "float", "0.95", "ops", "Saturation ratio threshold that triggers the rate-limit alert."),
    # Observability metrics exporter
    SettingSpec("OBSERVABILITY_METRICS_BACKEND", "str", '"noop"', "ops", "Metrics backend selector (noop / prometheus-client / statsd)."),
    SettingSpec("OBSERVABILITY_METRICS_BEARER_TOKEN", "str", "None", "ops", "Bearer token required to scrape the /metrics endpoint (None disables auth)."),
    SettingSpec("OBSERVABILITY_METRICS_STATSD_HOST", "str", '""', "ops", "StatsD host for the observability metrics exporter."),
    SettingSpec("OBSERVABILITY_METRICS_STATSD_PORT", "int", "8125", "ops", "StatsD UDP port for the observability metrics exporter."),
    SettingSpec("OBSERVABILITY_PROMETHEUS_NAMESPACE", "str", '"runmycampus"', "ops", "Prometheus metric namespace prefix."),
    # OIDC relying party
    SettingSpec("OIDC_PROVIDERS", "dict", "None", "identity", "OIDC relying-party provider configuration map."),
    # Ollama (local AI runtime)
    SettingSpec("OLLAMA_AUTO_DISCOVER", "bool", "True", "ops", "Probe common dev hosts for a reachable Ollama endpoint when unset/unreachable."),
    SettingSpec("OLLAMA_BASE_URL", "str", '"http://127.0.0.1:11434"', "ops", "Base URL of the local Ollama AI runtime."),
    SettingSpec("OLLAMA_BASE_URL_CANDIDATES", "str", '""', "ops", "Comma-separated candidate Ollama base URLs to probe."),
    SettingSpec("OLLAMA_REQUIRE_LIVE", "bool", "False", "ops", "Require a live Ollama backend (block rules fallback) when truthy."),
    # Operator alerting
    SettingSpec("OPERATOR_ALERT_DRY_RUN", "bool", "True", "ops", "Suppress real delivery of operator alerts (dry-run mode)."),
    SettingSpec("OPERATOR_ALERT_EMAIL", "str", '""', "ops", "Primary operator alert email address."),
    SettingSpec("OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY", "str", "None", "ops", "PagerDuty Events API integration key for operator alerts."),
    SettingSpec("OPERATOR_ALERT_RATE_LIMIT_PER_HOUR", "int", "50", "ops", "Max operator alerts dispatched per hour."),
    SettingSpec("OPERATOR_ALERT_SLACK_WEBHOOK_URL", "str", "None", "ops", "Slack incoming-webhook URL for operator alerts."),
    SettingSpec("OPERATOR_MFA_REQUIRED_ON_MANAGER", "bool", "True", "security", "Require MFA on the operator/manager console."),
    # Policy / ReBAC
    SettingSpec("POLICY_PDP_ENFORCEMENT_MODE", "str", '"advisory"', "security", "Policy decision-point enforcement mode (advisory / enforce)."),
    # Public status site
    SettingSpec("PUBLIC_STATUS_SITE_ORIGIN", "str", '""', "ops", "Origin of the public status site for cross-link generation."),
    # Redis / channels
    SettingSpec("REDIS_URL", "str", "None", "ops", "Redis connection URL for cache, channels, and WAL stream."),
    # RMC deployment / hub / edge / docs
    SettingSpec("RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION", "str", '"1"', "ops", "Auto-apply the offline bundle when provisioning an edge tenant."),
    SettingSpec("RMC_DEPLOYMENT_PROFILE", "str", '"online"', "ops", "Deployment profile selector (online / edge / offline)."),
    SettingSpec("RMC_EDGE_FALLBACK_ENABLED", "str", '""', "ops", "Enable edge-fallback middleware behavior when truthy."),
    SettingSpec("RMC_GENERATED_DOCS_DIR", "str", "None", "ops", "Override directory for generated trust-center / evidence docs."),
    SettingSpec("RMC_HUB_BASE_URL", "str", '""', "ops", "Base URL of the central RMC hub for offline-bundle sync."),
    # RMC IAM snapshot
    SettingSpec("RMC_IAM_SNAPSHOT_OFFLINE_TOKEN_TTL_HOURS", "int", "12", "identity", "TTL (hours) of offline IAM-snapshot tokens."),
    SettingSpec("RMC_IAM_SNAPSHOT_SIGNING_KEY", "str", "None", "identity", "Signing key for IAM snapshot tokens."),
    SettingSpec("RMC_IAM_SNAPSHOT_TTL_HOURS", "int", "168", "identity", "TTL (hours) of IAM snapshots."),
    SettingSpec("RMC_OFFLINE_CAPABILITY_TOKEN_TTL_HOURS", "int", "12", "identity", "TTL (hours) of write-capability offline tokens minted by devices-offline-token."),
    # RMC OIDC / OneRoster / SCIM tokens
    SettingSpec("RMC_OIDC_REDIRECT_BASE_URL", "str", '""', "identity", "Base URL used to build OIDC redirect URIs."),
    SettingSpec("RMC_ONEROSTER_ACCESS_TOKEN", "str", '""', "identity", "Static bearer token accepted by the OneRoster API (back-compat)."),
    SettingSpec("RMC_ONEROSTER_ALLOW_DEV_OPEN", "bool", "False", "identity", "DEV/TEST ONLY escape hatch: when no access token is configured, accept any bearer. Default off — the roster API fails closed in production (v4.01)."),
    SettingSpec("RMC_ONEROSTER_OAUTH_CLIENTS", "str", '""', "identity", "OneRoster OAuth2 client_credentials registry (client_id:secret pairs)."),
    SettingSpec("RMC_SCIM_ACCESS_TOKEN", "str", '""', "identity", "Bearer token accepted by the SCIM provisioning API."),
    # RMC operator / hosting
    SettingSpec("RMC_OPERATOR_ALERT_EMAIL", "str", '""', "ops", "Operator alert email used by the platform email matrix (falls back to OPERATOR_ALERT_EMAIL)."),
    SettingSpec("RMC_PRIMARY_HOST", "str", '""', "ops", "Primary host used to build absolute URLs in background tasks."),
    SettingSpec("RMC_PUBLIC_SITE_URL", "str", '""', "marketing", "Public site base URL used in newsletter/marketing links."),
    # RMC ReBAC
    SettingSpec("RMC_REBAC_DUAL_RUN_LOG_MISMATCH", "bool", "True", "security", "Log mismatches between legacy and ReBAC authorization during dual-run."),
    SettingSpec("RMC_REBAC_ENABLED", "bool", "True", "security", "Enable the ReBAC authorization engine."),
    SettingSpec("RMC_REBAC_ENFORCE_SENSITIVE", "bool", "False", "security", "Enforce (not just log) ReBAC decisions on sensitive resources."),
    # RMC RLS / sync signing keys
    SettingSpec("RMC_RLS_JWT_SIGNING_KEY", "str", '""', "security", "Signing key for row-level-security JWT tenant claims."),
    SettingSpec("RMC_SYNC_BUNDLE_SIGNING_KEY", "str", "None", "security", "Signing key for sync-engine delta bundles (falls back to SECRET_KEY)."),
    # RMC SAML 2.0 SP
    SettingSpec("RMC_SAML_ALLOW_RSA_SHA1", "bool", "False", "identity", "Allow legacy RSA-SHA1 SAML signature algorithm (default reject)."),
    SettingSpec("RMC_SAML_CLOCK_SKEW_SECONDS", "int", "300", "identity", "SAML clock-skew tolerance in seconds (clamped 0-3600)."),
    SettingSpec("RMC_SAML_HRD_MAPPING", "str", '""', "identity", "Home-realm-discovery domain-to-IdP mapping for SAML SSO."),
    SettingSpec("RMC_SAML_IDP_CERT_PEM", "str", '""', "identity", "IdP X.509 signing certificate (PEM) for SAML."),
    SettingSpec("RMC_SAML_IDP_SLO_URL", "str", '""', "identity", "IdP single-logout endpoint URL."),
    SettingSpec("RMC_SAML_IDP_SSO_URL", "str", '""', "identity", "IdP single-sign-on endpoint URL."),
    SettingSpec("RMC_SAML_LOGIN_BUTTON_LABEL", "str", '""', "identity", "Label shown on the SAML SSO login button."),
    SettingSpec("RMC_SAML_METADATA_CACHE_SECONDS", "int", "86400", "identity", "Cache TTL (seconds) for served SP metadata (floor 60)."),
    SettingSpec("RMC_SAML_METADATA_CONTACT_EMAIL", "str", '""', "identity", "Technical contact email published in SP metadata."),
    SettingSpec("RMC_SAML_METADATA_ORG_NAME", "str", '""', "identity", "Organization name published in SP metadata."),
    SettingSpec("RMC_SAML_METADATA_ORG_URL", "str", '""', "identity", "Organization URL published in SP metadata."),
    SettingSpec("RMC_SAML_REPLAY_DEFENSE_ENABLED", "bool", "True", "identity", "Reject replayed SAML assertion IDs (one-time-use defense)."),
    SettingSpec("RMC_SAML_REQUIRE_ASSERTION_SIGNATURE", "bool", "False", "identity", "Require the SAML Assertion element itself to be signed."),
    SettingSpec("RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION", "bool", "False", "identity", "Require successful EncryptedAssertion decryption on every response."),
    SettingSpec("RMC_SAML_REQUIRE_REDIRECT_SIGNATURE", "bool", "False", "identity", "Require inbound Redirect-binding signature verification."),
    SettingSpec("RMC_SAML_ALLOW_UNVERIFIED_ASSERTIONS", "bool", "False", "identity", "DEV/TEST ONLY escape hatch: allow ACS to provision+login from an unverified SAML assertion (no IdP cert / no signature). Never enable in production."),
    SettingSpec("RMC_SAML_REQUIRE_SIGNATURE", "bool", "True", "identity", "Require a signature on inbound SAML responses. Secure-by-default (v4.01); the ACS fails closed unless RMC_SAML_ALLOW_UNVERIFIED_ASSERTIONS is set."),
    SettingSpec("RMC_SAML_SIGNATURE_STRICT", "bool", "True", "identity", "Treat deps_missing signature verification as failure (strict mode)."),
    SettingSpec("RMC_SAML_SP_BASE_URL", "str", '""', "identity", "Service-provider base URL used to build SAML endpoints."),
    SettingSpec("RMC_SAML_SP_CERT_PEM", "str", '""', "identity", "Service-provider X.509 certificate (PEM)."),
    SettingSpec("RMC_SAML_SP_ENTITY_ID", "str", '""', "identity", "Service-provider SAML entity ID."),
    SettingSpec("RMC_SAML_SP_PRIVATE_KEY_PEM", "str", '""', "identity", "Service-provider private key (PEM) for SAML signing."),
    SettingSpec("RMC_SAML_SP_SIGNATURE_ALG", "str", '"rsa-sha256"', "identity", "Signature algorithm used when the SP signs SAML messages."),
    SettingSpec("RMC_SAML_SP_SIGN_LOGOUT", "bool", "False", "identity", "Sign outbound SP-initiated LogoutRequest/Response."),
    SettingSpec("RMC_SAML_TENANT_ATTR_MAP_OVERRIDES", "str", '""', "identity", "Per-tenant SAML attribute-map override registry."),
    # RMC setup wizard
    SettingSpec("RMC_WIZARD_ENGINE_OVERRIDES", "dict", "None", "ux", "Override map routing legacy wizard keys to new setup-studio engines."),
    # Schoolops email delivery
    SettingSpec("SCHOOLOPS_EMAIL_DELIVERY_RETRY_BACKOFF", "list", "[1, 5, 30]", "ops", "Per-attempt SMTP retry backoff in seconds (length = attempt count)."),
    SettingSpec("SCHOOLOPS_EMAIL_DELIVERY_SSE_HEARTBEAT_SECONDS", "int", "5", "ops", "Heartbeat cadence (seconds) for the email-health SSE stream."),
    SettingSpec("SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS", "int", "8", "ops", "Synchronous wall-clock budget (seconds) for in-request email sends."),
    SettingSpec("SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP", "int", "200", "ops", "Per-tenant sliding-window cap on transactional+bulk sends per hour."),
    SettingSpec("SCHOOLOPS_SENDGRID_REQUIRE_VERIFIED_WEBHOOK", "bool", "False", "security", "Reject SendGrid event-webhook posts whose ECDSA signature fails to verify (set 1 once the public key is configured)."),
    # Security strength
    SettingSpec("SECURITY_ENFORCE_MINIMUM_STRENGTH", "bool", "True", "security", "Enforce the minimum account security-strength middleware gate."),
    SettingSpec("SECURITY_PLATFORM_MINIMUM_SCORE", "int", "40", "security", "Minimum platform security score (0-100) required for access."),
    # Finance
    SettingSpec("SEND_FINANCE_SIGNALS", "bool", "True", "ops", "Emit finance domain signals (disable to suppress side effects)."),
    # Social media
    SettingSpec("SOCIAL_ASSET_CDN_BASE", "str", '""', "marketing", "CDN base URL prefix for processed social-media assets."),
    SettingSpec("SOCIAL_LIVE_FETCH_ENABLED", "bool", "False", "marketing", "Enable live outbound fetch from social-media providers."),
    SettingSpec("SOCIAL_LIVE_PUBLISH_ENABLED", "bool", "False", "marketing", "Enable live publishing to social-media providers."),
    # Tenant offboarding
    SettingSpec("TENANT_OFFBOARDING_PLATFORM_EMAILS", "str", '""', "ops", "Comma-separated platform notification emails for tenant offboarding."),
    # Messaging / email infrastructure (schoolops + communication waves)
    SettingSpec("SCHOOLOPS_EMAIL_ASYNC_USE_CELERY", "bool", "False", "communication", "Route transactional email sends through Celery instead of a daemon thread."),
    SettingSpec("SCHOOLOPS_EMAIL_DLQ_ENABLED", "bool", "False", "communication", "Enable the email dead-letter queue for failed sends."),
    SettingSpec("SCHOOLOPS_EMAIL_DLQ_MAX_REDRIVES", "int", "5", "communication", "Max redrive attempts before an email dead-letter is abandoned."),
    SettingSpec("SCHOOLOPS_EMAIL_SMTP_HOST_ALLOWLIST", "str", '""', "security", "Comma-separated SMTP host allowlist (SSRF guard for relay config)."),
    SettingSpec("SCHOOLOPS_EMAIL_STUCK_QUEUED_MINUTES", "int", "30", "communication", "Minutes a queued email may sit before the stuck-queue beat alerts."),
    SettingSpec("RMC_AUTO_ENQUEUE_OUTBOUND", "bool", "True", "communication", "Auto-enqueue SMS/WhatsApp to the outbound queue on provider failure."),
    SettingSpec("EMAIL_DKIM_RELAY_TRUSTED", "bool", "False", "communication", "Trust the upstream relay to apply DKIM signing (skip local signing check)."),
    SettingSpec("RMC_LIST_ID", "str", '""', "communication", "List-ID header value for bulk/newsletter email."),
    SettingSpec("RMC_LIST_UNSUBSCRIBE_MAILTO", "str", '""', "communication", "List-Unsubscribe mailto: target for bulk email."),
    SettingSpec("RMC_LIST_UNSUBSCRIBE_URL", "str", '""', "communication", "HTTPS one-click List-Unsubscribe endpoint for bulk email."),
    SettingSpec("RMC_COMPANY_LEGAL_NAME", "str", '"RunMyCampus"', "ops", "Legal company name for email footers / legal documents."),
    SettingSpec("RMC_COMPANY_POSTAL_ADDRESS", "str", '""', "ops", "Postal address for the CAN-SPAM-compliant email footer."),
    # SMS inbound webhook (communication wave)
    SettingSpec("RMC_SMS_HELP_REPLY", "str", '""', "communication", "Auto-reply body sent for an inbound SMS HELP keyword."),
    SettingSpec("RMC_SMS_WEBHOOK_ALLOW_QUERY_SECRET", "bool", "False", "security", "Allow SMS inbound webhook auth via a query-string secret (legacy fallback)."),
    SettingSpec("RMC_SMS_WEBHOOK_REQUIRE_TWILIO_SIGNATURE", "bool", "True", "security", "Require a valid Twilio signature on inbound SMS webhooks."),
    SettingSpec("RMC_SMS_WEBHOOK_SHARED_SECRET", "str", '""', "security", "Shared secret for verifying inbound SMS webhook requests."),
    # Security / auth posture
    SettingSpec("RMC_SUSPICIOUS_LOGIN_ALERTS_ENABLED", "bool", "True", "security", "Email the user on a new-device / suspicious login."),
    SettingSpec("RMC_SCIM_ALLOW_DEV_OPEN", "bool", "False", "security", "Allow open (unauthenticated) SCIM in dev only — never enable in prod."),
    SettingSpec("RATE_LIMIT_TRUSTED_PROXY_COUNT", "int", "0", "security", "Number of trusted reverse proxies when parsing X-Forwarded-For."),
    SettingSpec("SECURITY_POSTURE_REVIEW_NAG_ENABLED", "bool", "True", "security", "Nag operators to complete the periodic security-posture review."),
    SettingSpec("SIGNUP_MAX_PER_WINDOW", "int", "5", "security", "Max self-service signups permitted per rate-limit window."),
    SettingSpec("SIGNUP_RATE_WINDOW_SECONDS", "int", "3600", "security", "Signup rate-limit window length in seconds."),
    SettingSpec("SIGNUP_RESEND_COOLDOWN_SECONDS", "int", "120", "security", "Cooldown between verification-email resend attempts per email and IP."),
    SettingSpec("SIGNUP_RESEND_DAILY_CAP", "int", "5", "security", "Daily verification-email resend cap per email address."),
    # Compliance
    SettingSpec("COMPLIANCE_AUDIT_ACCESS_LOG_MIDDLEWARE_WRITES", "bool", "True", "compliance", "Whether the audit-access-log middleware persists access rows."),
    SettingSpec("COMPLIANCE_ERASURE_SLA_DAYS", "int", "30", "compliance", "SLA window (days) for fulfilling a GDPR erasure request."),
)


def all_setting_names() -> set[str]:
    """Return the set of registered setting names."""
    return {spec.name for spec in SETTINGS_REGISTRY}


def find_spec(name: str) -> SettingSpec | None:
    """Return the SettingSpec for ``name``, or ``None`` if not registered."""
    for spec in SETTINGS_REGISTRY:
        if spec.name == name:
            return spec
    return None


__all__ = [
    "SettingSpec",
    "SETTINGS_REGISTRY",
    "all_setting_names",
    "find_spec",
]
