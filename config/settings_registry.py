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

    # ---- AI / LLM ------------------------------------------------------------
    SettingSpec("AI_ALLOW_RULES_FALLBACK", "bool", "True", "ai", "Fallback to deterministic rules when AI provider is unreachable."),
    SettingSpec("AI_COPILOT_ENABLED", "bool", "False", "ai", "Master switch for the in-product AI copilot surface."),
    SettingSpec("AI_EMBEDDING_OLLAMA_MODEL", "str", '"all-minilm"', "ai", "Ollama embedding model name."),
    SettingSpec("AI_GATEWAY_ENABLED", "bool", "True", "ai", "Master switch for the AI gateway abstraction."),
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
    SettingSpec("CELERY_BROKER_URL", "str", '""', "ops", "Celery broker URL (Redis / RabbitMQ); empty disables tasks."),
    SettingSpec("OBSERVABILITY_API_KEY", "str", '""', "ops", "Optional API key for the observability ingestion endpoint."),
    SettingSpec("RUM_INGEST_KEY", "str", '""', "ops", "Real User Monitoring beacon ingest key."),
    SettingSpec("OPENSEARCH_DSN", "str", '""', "ops", "OpenSearch / Elasticsearch DSN for log shipping."),
    SettingSpec("RUNNING_TESTS", "bool", "False", "ops", "Set automatically when pytest / Django test runner is active."),
    SettingSpec("WEASYPRINT_BASEURL", "str", '""', "ops", "Base URL passed to WeasyPrint for relative asset resolution."),

    # ---- Compliance / audit -------------------------------------------------
    SettingSpec("COMPLIANCE_ALERTS", "dict", "{}", "compliance", "Alert routing config for compliance violations."),
    SettingSpec("COMPLIANCE_DASHBOARD_CACHE_SECONDS", "int", "300", "compliance", "Compliance dashboard cache TTL."),
    SettingSpec("COMPLIANCE_EXPORT_MAX_ROWS", "int", "100000", "compliance", "Cap on rows per compliance export."),
    SettingSpec("DATA_RETENTION", "dict", "{}", "compliance", "Per-model retention overrides (days)."),
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
    SettingSpec("CSP_ENFORCE", "bool", "False", "security", "Switch CSP from Report-Only to enforced (Content-Security-Policy header)."),
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
    SettingSpec("DEFAULT_SCHOOL_TIMEZONE", "str", '"UTC"', "ops", "Default timezone applied to new schools."),
    SettingSpec("PLATFORM_DEFAULT_TIMEZONE", "str", '"UTC"', "ops", "Platform-wide default timezone."),
    SettingSpec("PLATFORM_DEFAULT_GRADING_SCALE", "str", '""', "academics", "Default grading scale slug for new schools."),

    # ---- Reports / OCR -----------------------------------------------------
    SettingSpec("MARKSHEET_OCR_COMMAND", "str", '""', "academics", "External OCR command line for marksheet ingestion."),
    SettingSpec("REPORT_SHARE_DAYS", "int", "30", "academics", "Days a shared-report link remains valid."),

    # ---- Comms providers ---------------------------------------------------
    SettingSpec("REGIONAL_FROM_EMAIL", "str", '""', "communication", "Per-region overridden DEFAULT_FROM_EMAIL."),
    SettingSpec("SLACK_WEBHOOK_URL", "str", '""', "communication", "Slack incoming webhook for ops alerts."),
    SettingSpec("SMS_API_TOKEN", "str", '""', "communication", "Generic SMS provider API token."),
    SettingSpec("SMS_API_URL", "str", '""', "communication", "Generic SMS provider base URL."),
    SettingSpec("TWILIO_ACCOUNT_SID", "str", '""', "communication", "Twilio account SID."),
    SettingSpec("TWILIO_AUTH_TOKEN", "str", '""', "communication", "Twilio auth token."),
    SettingSpec("WHATSAPP_BASE_URL", "str", '""', "communication", "Optional override of the WhatsApp Cloud API base URL."),

    # ---- Support / help-desk -----------------------------------------------
    SettingSpec("SUPPORT_AI_AUTO_TRIAGE_ON_CREATE", "bool", "False", "ops", "Run AI triage on every new support ticket."),
    SettingSpec("SUPPORT_AI_KB_CONTEXT", "dict", "{}", "ops", "AI KB context map for support triage."),
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
    SettingSpec("WEBHOOK_P95_LATENCY_SLO_MS", "int", "1500", "ops", "Webhook delivery p95 latency SLO."),
    SettingSpec("WEBHOOK_SUCCESS_SLO_PERCENT", "float", "99.0", "ops", "Webhook delivery success-rate SLO percent."),

    # ---- Tenant lifecycle --------------------------------------------------
    SettingSpec("TENANT_LIFECYCLE_CHURN_INACTIVITY_DAYS", "int", "30", "ops", "Days of inactivity before the churn signal fires."),
    SettingSpec("TENANT_LIFECYCLE_CHURN_PAYMENT_FAILED_DAYS", "int", "7", "ops", "Days after payment failure before churn signal fires."),
    SettingSpec("TENANT_LIFECYCLE_FIRST_ACTION_STALL_DAYS", "int", "7", "ops", "Days a fresh tenant can stall before nudge."),
    SettingSpec("TENANT_LIFECYCLE_ONBOARDING_STALL_DAYS", "int", "14", "ops", "Days an onboarding tenant can stall before escalation."),

    # ---- Misc / runbooks ---------------------------------------------------
    SettingSpec("CONTROL_PLANE_RUNBOOKS_URL", "str", '""', "ops", "Public URL where ops runbooks live."),
    SettingSpec("FIFTY_PCT_REDUCTION_CLAIM_ALLOWED", "bool", "False", "marketing", "Honesty gate — only show '50% reduction' claim with proof."),
    SettingSpec("RUNMYCAMPUS_DEMO_ENABLED", "bool", "False", "marketing", "Enable in-product demo flows."),
    SettingSpec("RUNMYCAMPUS_DEMO_MODE", "str", '""', "marketing", "Demo mode label (sandbox / staging / live)."),
    SettingSpec("TESTING_MATRIX_REGIONS", "tuple[str]", "()", "ops", "Regions exercised by the multi-region test matrix."),
    SettingSpec("WEDGE_14_22_OPERATOR_PLAYBOOK_URL", "str", '""', "ops", "Operator playbook URL for the 14-22 wedge program."),
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
