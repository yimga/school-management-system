"""Operational center frame copy + nav groups for compact control-plane workbenches."""

from __future__ import annotations

from typing import Any


def _groups(*items: dict[str, str]) -> list[dict[str, str]]:
    return list(items)


CONFIGURATION_CENTER_NAV_GROUPS = _groups(
    {
        "key": "operating-models",
        "label": "Operating Models",
        "title": "Blueprints, packages, packs, policies",
        "body": "Operators see model readiness before opening advanced configuration.",
    },
    {
        "key": "runtime-governance",
        "label": "Runtime Governance",
        "title": "Change requests, rules, registries",
        "body": "Approvals, health, and drift stay in the command layer.",
    },
    {
        "key": "trust-money",
        "label": "Trust + Money",
        "title": "Compliance, security, billing",
        "body": "External dependencies remain explicit instead of hidden behind status color.",
    },
)

CHANGE_REQUESTS_NAV_GROUPS = _groups(
    {
        "key": "queue",
        "label": "Queue",
        "title": "Pending and scheduled changes",
        "body": "Risk, approver, tenant scope, and status are visible before apply.",
    },
    {
        "key": "lifecycle",
        "label": "Lifecycle",
        "title": "Requested → approved → applied",
        "body": "Scheduling, cancellation, audit, and rollback posture stay in one queue.",
    },
    {
        "key": "health",
        "label": "Health",
        "title": "Monitor before apply",
        "body": "Registry health and external blockers remain explicit through rollout.",
    },
)

SCHOOL_CONFIGURATION_NAV_GROUPS = _groups(
    {
        "key": "profile-academics",
        "label": "Profile + academics",
        "title": "School profile, years, classes, grading",
        "body": "Tenant-safe structure before portals and reports go live.",
    },
    {
        "key": "money-apps",
        "label": "Money + apps",
        "title": "Fees, apps, workflows, offline",
        "body": "Honest external posture for payments and marketplace installs.",
    },
    {
        "key": "brand-security",
        "label": "Brand + security",
        "title": "Branding, theme, audit",
        "body": "School-visible branding without platform registry controls.",
    },
)

BLUEPRINT_MARKETPLACE_NAV_GROUPS = _groups(
    {
        "key": "preview",
        "label": "Preview",
        "title": "Simulate blueprint impact",
        "body": "Dependency, approval, and rollback posture before install.",
    },
    {
        "key": "approval",
        "label": "Approval",
        "title": "Request when risk requires it",
        "body": "Governed path when tenant operating model changes need review.",
    },
    {
        "key": "history",
        "label": "History",
        "title": "Installations and rollback",
        "body": "Monitor applied blueprints with audit and health signals.",
    },
)

PACK_MARKETPLACE_NAV_GROUPS = _groups(
    {
        "key": "preview",
        "label": "Preview",
        "title": "Simulate pack impact",
        "body": "Tenant boundary and prerequisites visible before apply.",
    },
    {
        "key": "approval",
        "label": "Approval",
        "title": "Governed install path",
        "body": "Risk, scheduling, and audit when packs need operator sign-off.",
    },
    {
        "key": "rollback",
        "label": "Rollback",
        "title": "Deactivate or roll back",
        "body": "Health and rollback posture stay on the installation record.",
    },
)

MIGRATION_CENTER_NAV_GROUPS = _groups(
    {
        "key": "ingest",
        "label": "Ingest",
        "title": "Upload or select template",
        "body": "Preview and map fields before validation runs.",
    },
    {
        "key": "quality",
        "label": "Quality",
        "title": "Quarantine and score",
        "body": "Duplicates, invalid rows, and quarantine state before apply.",
    },
    {
        "key": "audit",
        "label": "Audit",
        "title": "Apply with rollback",
        "body": "Audit trail and operator health remain one click away.",
    },
)

BILLING_COMMAND_NAV_GROUPS = _groups(
    {
        "key": "packages",
        "label": "Packages",
        "title": "Compare entitlements",
        "body": "Package comparison and upgrade posture without hidden PSP claims.",
    },
    {
        "key": "usage",
        "label": "Usage",
        "title": "Meters and ledger",
        "body": "Usage API and billing impact previews stay operator-visible.",
    },
    {
        "key": "psp",
        "label": "PSP",
        "title": "External settlement honest",
        "body": "Live PSP, settlement, and manual fallback remain explicit blockers.",
    },
)

APP_CATALOG_NAV_GROUPS = _groups(
    {
        "key": "browse",
        "label": "Browse",
        "title": "Sandbox-first catalog",
        "body": "Pick a school once, preview impact per app, then install to sandbox.",
    },
    {
        "key": "trust",
        "label": "Trust",
        "title": "Scopes and signals",
        "body": "Trust signals and scope review before production promotion.",
    },
    {
        "key": "governance",
        "label": "Governance",
        "title": "Marketplace console",
        "body": "Listing reviews, kill switches, and revenue share stay linked.",
    },
)

SANDBOX_INSPECTOR_NAV_GROUPS = _groups(
    {
        "key": "stage",
        "label": "Stage",
        "title": "Pre-activation installs",
        "body": "Every install starts in sandbox until school validation completes.",
    },
    {
        "key": "promote",
        "label": "Promote",
        "title": "Production promotion",
        "body": "Promote only after operator and school sign-off.",
    },
    {
        "key": "governance",
        "label": "Governance",
        "title": "Blast-radius control",
        "body": "Governance console and catalog stay one click away.",
    },
)

COMPATIBILITY_MATRIX_NAV_GROUPS = _groups(
    {
        "key": "gates",
        "label": "Gates",
        "title": "Country and plan fit",
        "body": "Country, blueprint family, and plan-tier gates per app.",
    },
    {
        "key": "matrix",
        "label": "Matrix",
        "title": "Paginated rules",
        "body": "Install rules stay scannable within page-fold limits.",
    },
    {
        "key": "catalog",
        "label": "Catalog",
        "title": "Sandbox install path",
        "body": "Compatibility is evaluated before sandbox install in the app catalog.",
    },
)

INSTALLATION_HEALTH_NAV_GROUPS = _groups(
    {
        "key": "glance",
        "label": "Glance",
        "title": "Active installs tracked",
        "body": "Counts and hub links stay above the paginated health table.",
    },
    {
        "key": "health",
        "label": "Health",
        "title": "Last check per install",
        "body": "Refresh actions and status without leaving the queue.",
    },
    {
        "key": "sandbox",
        "label": "Sandbox",
        "title": "Pre-activation path",
        "body": "Sandbox inspector and catalog stay one click away.",
    },
)

TENANT_IMPORT_NAV_GROUPS = _groups(
    {
        "key": "roster",
        "label": "Roster",
        "title": "Students and guardians",
        "body": "Unlock attendance, fees, reports, and parent access.",
    },
    {
        "key": "staff",
        "label": "Staff",
        "title": "Teachers and roles",
        "body": "Load staff before classes, subjects, and approval flows.",
    },
    {
        "key": "migration",
        "label": "Migration",
        "title": "Connector handoff",
        "body": "SIS exports and Migration Cloud intake on one landing.",
    },
)

TENANT_BLUEPRINT_NAV_GROUPS = _groups(
    {
        "key": "preview",
        "label": "Preview",
        "title": "School impact visible",
        "body": "Tenant-safe blueprints only; blockers before apply.",
    },
    {
        "key": "approval",
        "label": "Approval",
        "title": "Request when required",
        "body": "Platform governance when risk needs operator sign-off.",
    },
    {
        "key": "config",
        "label": "Config",
        "title": "School configuration",
        "body": "Settings, packs, and audit trail stay linked.",
    },
)

TENANT_PACK_NAV_GROUPS = _groups(
    {
        "key": "simulate",
        "label": "Simulate",
        "title": "Preview pack impact",
        "body": "Tenant boundary and prerequisites before apply.",
    },
    {
        "key": "apply",
        "label": "Apply",
        "title": "Approved low-risk changes",
        "body": "Deactivate and rollback on the installation record.",
    },
    {
        "key": "config",
        "label": "Config",
        "title": "School configuration",
        "body": "Guided setup without platform-only controls.",
    },
)

TENANT_APP_CATALOG_NAV_GROUPS = _groups(
    {
        "key": "browse",
        "label": "Browse",
        "title": "Sandbox-first catalog",
        "body": "Scopes, billing model, and install impact before activation.",
    },
    {
        "key": "trust",
        "label": "Trust",
        "title": "Consent and webhooks",
        "body": "Partner status and uninstall posture stay visible.",
    },
    {
        "key": "config",
        "label": "Config",
        "title": "School settings",
        "body": "Upgrade and external PSP honesty before paid apps.",
    },
)

PRICING_PACKAGES_NAV_GROUPS = _groups(
    {
        "key": "compare",
        "label": "Compare",
        "title": "Package fit",
        "body": "Modules, add-ons, and honest limits before rollout.",
    },
    {
        "key": "psp",
        "label": "PSP",
        "title": "External settlement",
        "body": "Live PSP and settlement proof required — no fake unlimiteds.",
    },
    {
        "key": "demo",
        "label": "Demo",
        "title": "Guided buyer path",
        "body": "Book demo and review trust posture before purchase.",
    },
)

MONEY_CENTER_NAV_GROUPS = _groups(
    {
        "key": "invoices",
        "label": "Invoices",
        "title": "Collect in-product",
        "body": "Invoices and receipts with manual fallback when PSP is external.",
    },
    {
        "key": "readiness",
        "label": "Readiness",
        "title": "Payment gateway honest",
        "body": "No fake live collection; settlement proof required.",
    },
    {
        "key": "usage",
        "label": "Usage",
        "title": "Entitlements and meters",
        "body": "Package comparison and billing impact before upgrade.",
    },
)

PAYMENT_READINESS_NAV_GROUPS = _groups(
    {
        "key": "status",
        "label": "Status",
        "title": "Corridor honesty",
        "body": "Ready, fallback-only, or needs setup — never fake live charges.",
    },
    {
        "key": "gateway",
        "label": "Gateway",
        "title": "Rail health",
        "body": "Metadata-only checks for CARD/BANK until PSP onboarding completes.",
    },
    {
        "key": "next",
        "label": "Next action",
        "title": "One clear CTA",
        "body": "Setup credentials or open Money Center without leaving tenant scope.",
    },
)

THEME_EXPERIENCE_NAV_GROUPS = _groups(
    {
        "key": "palette",
        "label": "Palette",
        "title": "Brand colors live",
        "body": "Header, sidebar, hero, buttons, and status must preview before publish.",
    },
    {
        "key": "roles",
        "label": "Roles",
        "title": "Every portal surface",
        "body": "Admin, teacher, parent, and student dashboards wear the same tokens.",
    },
    {
        "key": "publish",
        "label": "Publish",
        "title": "Guarded apply",
        "body": "Preview confirmation before high-impact theme publish.",
    },
)

ONBOARDING_NAV_GROUPS = _groups(
    {
        "key": "progress",
        "label": "Progress",
        "title": "Activation checklist",
        "body": "Evidence-backed steps from this school’s real records.",
    },
    {
        "key": "import",
        "label": "Import",
        "title": "Roster and SIS",
        "body": "Migration quality and handoff stay visible before launch.",
    },
    {
        "key": "next",
        "label": "Next",
        "title": "One primary action",
        "body": "Resume the next pending step without operator surfaces.",
    },
)

MARKETPLACE_GOVERNANCE_NAV_GROUPS = _groups(
    {
        "key": "listings",
        "label": "Listings",
        "title": "Review and publish",
        "body": "Publisher listings, scopes, and compatibility before go-live.",
    },
    {
        "key": "security",
        "label": "Security",
        "title": "Posture and kill switches",
        "body": "Contain blast radius without endless table scroll.",
    },
    {
        "key": "revenue",
        "label": "Revenue",
        "title": "Payouts and share",
        "body": "Revenue share and payout triage in paginated queues.",
    },
)


def configuration_center_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform Configuration Center",
        "center_title": "Operations",
        "center_purpose": (
            "Governed facade over existing SiteConfig, Studio OS, marketplace, "
            "metadata, runtime, security, billing, and automation systems."
        ),
        "configuration_nav_groups": CONFIGURATION_CENTER_NAV_GROUPS,
    }


def change_requests_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Configuration governance",
        "center_title": "Change requests",
        "center_purpose": (
            "Approval, scheduling, application, cancellation, audit, and rollback "
            "posture for governed configuration changes."
        ),
        "status_badge_text": "Approval queue",
        "operational_nav_groups": CHANGE_REQUESTS_NAV_GROUPS,
    }


def school_configuration_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "Setup · this school",
        "center_title": "Configuration",
        "center_purpose": (
            "School settings, blueprints, packs, imports, apps, money, workflows, "
            "offline posture, audit, and security — tenant scoped only. School readiness, "
            "blockers, and next best action stay visible without exposing platform-only actions."
        ),
        # Live status comes from masthead chips / setup_health — not a static badge.
        "status_badge_text": "",
        "operational_nav_groups": SCHOOL_CONFIGURATION_NAV_GROUPS,
    }


def blueprint_marketplace_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform operators",
        "center_title": "Blueprint Marketplace",
        "center_purpose": (
            "Preview, simulate impact, request approval, schedule, apply, monitor, "
            "and roll back tenant operating models with visible external blockers."
        ),
        "status_badge_text": "Approval aware",
        "operational_nav_groups": BLUEPRINT_MARKETPLACE_NAV_GROUPS,
    }


def pack_marketplace_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform operators",
        "center_title": "Pack installation",
        "center_purpose": (
            "Preview, simulate, impact-analyze, request approval, schedule, apply, "
            "monitor, deactivate, and roll back installable platform packs."
        ),
        "status_badge_text": "Tenant boundary visible",
        "operational_nav_groups": PACK_MARKETPLACE_NAV_GROUPS,
    }


def migration_center_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Implementation operators",
        "center_title": "Migration Center",
        "center_purpose": (
            "Upload or select a template, preview, map fields, validate, quarantine "
            "issues, score data quality, apply, audit, and preserve rollback posture."
        ),
        "status_badge_text": "Rollback aware",
        "operational_nav_groups": MIGRATION_CENTER_NAV_GROUPS,
    }


def billing_command_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Money · fleet",
        "center_title": "Platform billing",
        "center_purpose": (
            "Package comparison, entitlement diff, usage meters, billing impact "
            "previews, upgrade and downgrade requests, external PSP status, manual "
            "fallback, and revenue share posture."
        ),
        "status_badge_text": "",
        "operational_nav_groups": BILLING_COMMAND_NAV_GROUPS,
    }


def marketplace_governance_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform marketplace operators",
        "center_title": "Marketplace governance",
        "center_purpose": (
            "Publishers, listing reviews, security posture, kill switches, and "
            "revenue share — paginated queues so the console stays within page-fold limits."
        ),
        "status_badge_text": "Governed",
        "operational_nav_groups": MARKETPLACE_GOVERNANCE_NAV_GROUPS,
    }


def app_catalog_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform marketplace operators",
        "center_title": "App Catalog Governance",
        "center_purpose": (
            "Browse installable apps with trust signals, scope review, and sandbox-first "
            "rollout — without endless scrolling."
        ),
        "status_badge_text": "Sandbox first",
        "operational_nav_groups": APP_CATALOG_NAV_GROUPS,
    }


def sandbox_inspector_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform operators",
        "center_title": "Sandbox inspector",
        "center_purpose": (
            "Installations awaiting promotion — paginated list with promote-to-production "
            "actions."
        ),
        "status_badge_text": "Pre-activation",
        "operational_nav_groups": SANDBOX_INSPECTOR_NAV_GROUPS,
    }


def compatibility_matrix_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform operators",
        "center_title": "Compatibility matrix",
        "center_purpose": (
            "Country, blueprint family, and plan-tier gates per app — paginated so install "
            "rules stay scannable."
        ),
        "status_badge_text": "Install gates",
        "operational_nav_groups": COMPATIBILITY_MATRIX_NAV_GROUPS,
    }


def installation_health_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform operators",
        "center_title": "Installation health",
        "center_purpose": (
            "Last health check per active install — paginated table with refresh actions."
        ),
        "status_badge_text": "",
        "operational_nav_groups": INSTALLATION_HEALTH_NAV_GROUPS,
    }


def marketplace_incident_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform operators",
        "center_title": "Marketplace incidents",
        "center_purpose": (
            "Central place for marketplace-related incidents. Use the support dashboard "
            "for the full incident queue."
        ),
        "status_badge_text": "",
        "operational_nav_groups": MARKETPLACE_GOVERNANCE_NAV_GROUPS,
    }


def package_rollout_frame_context() -> dict[str, Any]:
    return {
        "page_provides_own_h1": True,
        "center_eyebrow": "Platform operators",
        "center_title": "Package rollout",
        "center_purpose": "Staged package rollout across tenant installations.",
        "status_badge_text": "",
        "operational_nav_groups": BLUEPRINT_MARKETPLACE_NAV_GROUPS,
    }


def tenant_import_setup_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "School administrators",
        "center_title": "School Import Setup",
        "center_purpose": (
            "One import landing for rosters, staff, balances, and full SIS migration handoff."
        ),
        "status_badge_text": "Import readiness",
        "operational_nav_groups": TENANT_IMPORT_NAV_GROUPS,
    }


def tenant_blueprint_setup_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "School administrators",
        "center_title": "School Blueprint Setup",
        "center_purpose": (
            "Tenant-safe blueprints only. Preview school impact and request approval when "
            "platform governance is required."
        ),
        "status_badge_text": "Tenant-safe",
        "operational_nav_groups": TENANT_BLUEPRINT_NAV_GROUPS,
    }


def tenant_pack_setup_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "School administrators",
        "center_title": "Shape how your school works",
        "center_purpose": (
            "Choose tenant-safe workflows, dashboards, policies, and experiences. Preview every "
            "change, simulate impact, and keep approval and rollback controls in one full-canvas workspace."
        ),
        "status_badge_text": "Tenant-safe",
        "operational_nav_groups": TENANT_PACK_NAV_GROUPS,
    }


def tenant_app_catalog_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "School administrators",
        "center_title": "School App Catalog",
        "center_purpose": (
            "Sandbox-first school app installation with visible scopes, billing model, install "
            "impact, webhook health, and uninstall posture."
        ),
        "status_badge_text": "Tenant-safe",
        "operational_nav_groups": TENANT_APP_CATALOG_NAV_GROUPS,
    }


def money_center_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "Money · this school",
        "center_title": "Finance",
        "center_purpose": (
            "Invoices, fees, payment readiness, usage meters, and manual fallback — "
            "tenant-scoped money desk twin of platform billing."
        ),
        "status_badge_text": "",
        "operational_nav_groups": MONEY_CENTER_NAV_GROUPS,
    }


def payment_readiness_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "Finance",
        "center_title": "Payment Readiness Center",
        "center_purpose": (
            "Honest corridor status: metadata-only health checks — no live charges; "
            "CARD/BANK stay external until PSP onboarding."
        ),
        "status_badge_text": "Payment posture",
        "operational_nav_groups": PAYMENT_READINESS_NAV_GROUPS,
    }


def theme_experience_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "School brand",
        "center_title": "Theme & Experience",
        "center_purpose": (
            "Pick palette, preview every role surface, then publish tenant brand tokens safely."
        ),
        "status_badge_text": "Tenant scoped",
        "operational_nav_groups": THEME_EXPERIENCE_NAV_GROUPS,
    }


def onboarding_activation_frame_context() -> dict[str, Any]:
    return {
        "center_eyebrow": "School activation",
        "center_title": "School activation checklist",
        "center_purpose": (
            "Signup-to-daily-ops path: blueprint, import, brand, readiness — one next action."
        ),
        "status_badge_text": "Tenant scoped",
        "operational_nav_groups": ONBOARDING_NAV_GROUPS,
    }


# Super marketplace workbenches: admin bridge lives in operational frame actions, not strip.
MARKETPLACE_OPERATIONAL_FRAME_URL_NAMES = frozenset(
    {
        "app_catalog",
        "marketplace_governance",
        "blueprint_marketplace",
        "marketplace_compatibility",
        "marketplace_installation_health",
        "marketplace_sandbox_inspector",
        "marketplace_incident_dashboard",
        "package_rollout",
    }
)


def enrich_operational_frame_context(
    request, frame_ctx: dict[str, Any]
) -> dict[str, Any]:
    """Operational frame context (platform-admin tertiary CTA retired)."""
    del request
    return dict(frame_ctx)


def pricing_packages_frame_context(*, live_psp_caveat: str = "") -> dict[str, Any]:
    purpose = live_psp_caveat or (
        "Entitlements, usage posture, support, marketplace access, and PSP caveats stay "
        "visible before a buyer chooses a package."
    )
    return {
        "center_eyebrow": "Buyers and operators",
        "center_title": "Packages",
        "center_purpose": purpose,
        "status_badge_text": "Payment readiness honest",
        "operational_nav_groups": PRICING_PACKAGES_NAV_GROUPS,
    }
