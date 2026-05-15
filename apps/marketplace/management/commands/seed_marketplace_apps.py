"""
Platform bootstrap: Seed first-party Marketplace apps and approved listings so the
Manager App catalog shows installable apps. Idempotent (update_or_create by slug).
Run: python manage.py seed_marketplace_apps
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketplace.models import (
    AppScope,
    AppVersionCompat,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)

# Phase 9: governed compatibility defaults merged into listing JSON (idempotent).
PHASE9_DEFAULT_COMPAT = {
    "countries": ["US", "CA", "CM"],
    "plan_tiers": ["standard", "enterprise"],
    "blueprint_families": ["k12_core"],
    "workflow_families": ["operations_default"],
    "recommended_sectors": ["PUBLIC", "PRIVATE_K12"],
    "min_rmc_version": "2025.03",
    "sandbox_recommended": True,
    "rollback_summary": (
        "Sandbox-first app install; uninstall from Installed apps; metadata packs use Pack rollback."
    ),
}


def _phase9_enrich_catalog(stdout, style) -> None:
    """Scopes from manifest, compatibility matrix, and platform min version hints."""
    pub = PublisherOrganization.objects.filter(slug="runmycampus-first-party").first()
    if not pub:
        return
    touched = 0
    for app in MarketplaceApp.objects.filter(publisher=pub, is_active=True):
        manifest = app.manifest or {}
        scopes = manifest.get("scopes") or []
        if isinstance(scopes, list):
            for code in scopes:
                if not code:
                    continue
                c = str(code).strip()[:80]
                sensitive = c.lower() in ("ai", "identity", "evals", "migration_import")
                _, created = AppScope.objects.get_or_create(
                    app=app,
                    scope_code=c,
                    defaults={
                        "description": f"Declared in manifest ({app.slug})",
                        "sensitive": sensitive,
                    },
                )
                if created:
                    touched += 1
        listing = getattr(app, "listing", None)
        if listing:
            cur = (
                dict(listing.compatibility)
                if isinstance(listing.compatibility, dict)
                else {}
            )
            merged = {**PHASE9_DEFAULT_COMPAT, **cur}
            if merged != cur:
                listing.compatibility = merged
                listing.save(update_fields=["compatibility", "updated_at"])
                touched += 1
        if not AppVersionCompat.objects.filter(app=app).exists():
            AppVersionCompat.objects.create(
                app=app,
                platform_min_version="2025.03",
                app_version_min=app.version or "1.0",
                app_version_max="",
                notes="Phase 9 seed — compatibility matrix",
            )
            touched += 1
    if touched:
        stdout.write(
            style.SUCCESS(
                f"Phase 9 catalog enrichment: {touched} create/update operations."
            )
        )


# First-party apps to show in App catalog (installable after seed)
# manifest.wedge_ids: every value 1–45 must appear in at least one app (replication engine / kit tagging).
FIRST_PARTY_APPS = [
    {
        "slug": "international-k12-core-starter",
        "name": "International K–12 core starter",
        "description": "First-party international school starter: DNA alignment, region-aware defaults, and spine links to LMS and migration.",
        "version": "1.0",
        "manifest": {
            "scopes": ["setup", "academics", "communication"],
            "widgets": [],
            "wedge_ids": [1, 17],
        },
    },
    {
        "slug": "advanced-analytics-pack",
        "name": "Advanced Analytics Pack",
        "description": "First-party analytics and reporting enhancements for dashboards and exports.",
        "version": "1.0",
        "manifest": {"scopes": [], "widgets": [], "wedge_ids": [1, 4, 31]},
    },
    {
        "slug": "ai-grading-assistant",
        "name": "AI Grading Assistant",
        "description": "First-party AI-assisted grading and feedback for assessments.",
        "version": "1.0",
        "manifest": {"scopes": ["evals", "ai"], "widgets": [], "wedge_ids": [26, 27, 28, 39]},
    },
    {
        "slug": "executive-insights",
        "name": "Executive Insights",
        "description": "First-party executive dashboards and KPI summaries.",
        "version": "1.0",
        "manifest": {"scopes": ["analytics"], "widgets": [], "wedge_ids": [1, 4, 5, 41]},
    },
    {
        "slug": "compliance-export",
        "name": "Compliance Export",
        "description": "First-party compliance reporting and export for audits.",
        "version": "1.0",
        "manifest": {"scopes": ["compliance"], "widgets": [], "wedge_ids": [4, 20]},
    },
    {
        "slug": "sso-identity",
        "name": "SSO / Identity",
        "description": "First-party SSO and identity provider integration (OIDC, SAML).",
        "version": "1.0",
        "manifest": {"scopes": ["identity"], "widgets": [], "wedge_ids": [2, 44, 45]},
    },
    {
        "slug": "advanced-workflow-builder",
        "name": "Advanced Workflow Builder",
        "description": "First-party advanced workflow design and automation.",
        "version": "1.0",
        "manifest": {"scopes": ["workflow"], "widgets": [], "wedge_ids": [14, 16, 21, 22]},
    },
    {
        "slug": "migration-connector-pack",
        "name": "Migration Connector Pack",
        "description": "First-party migration and import connectors for CSV/XLSX and legacy data.",
        "version": "1.0",
        "manifest": {"scopes": ["migration_import"], "widgets": [], "wedge_ids": [1, 44]},
    },
    {
        "slug": "premium-communication-pack",
        "name": "Premium Communication Pack",
        "description": "First-party communication and announcement enhancements.",
        "version": "1.0",
        "manifest": {
            "scopes": ["communication"],
            "widgets": [],
            "wedge_ids": [1, 5, 15, 24, 25],
        },
    },
    {
        "slug": "transport-bus-tracker",
        "name": "Transport / Bus Tracker",
        "description": "First-party transport and bus tracking module.",
        "version": "1.0",
        "manifest": {"scopes": ["transport"], "widgets": [], "wedge_ids": [14, 33]},
    },
    {
        "slug": "district-pack",
        "name": "District Pack",
        "description": "First-party district and multi-school governance and reporting.",
        "version": "1.0",
        "manifest": {"scopes": ["district"], "widgets": [], "wedge_ids": [4, 22]},
    },
    {
        "slug": "enterprise-governance-console",
        "name": "Enterprise governance console",
        "description": "First-party cross-campus governance, audit exports, and break-glass workflows (Enterprise tier).",
        "version": "1.0",
        "manifest": {
            "scopes": ["compliance", "analytics"],
            "widgets": [],
            "wedge_ids": [4, 20, 41],
            "required_commercial_tier": "enterprise",
            "pricing_type": "paid",
            "price_display": "Enterprise agreement",
            "upgrade_message": "Upgrade to Enterprise to install this app on production tenants.",
        },
    },
    {
        "slug": "global-readiness-starter",
        "name": "Global readiness starter",
        "description": "First-party locale, grading, and term-structure helpers aligned to education profiles.",
        "version": "1.0",
        "manifest": {
            "scopes": ["setup", "academics"],
            "widgets": [],
            "wedge_ids": [1, 17],
            "required_commercial_tier": "free",
            "category": "global",
        },
    },
    {
        "slug": "private-school-pack",
        "name": "Private School Pack",
        "description": "First-party private-school lifecycle and family engagement.",
        "version": "1.0",
        "manifest": {"scopes": ["admissions", "finance"], "widgets": [], "wedge_ids": [15]},
    },
    {
        "slug": "admissions-lead-tracker",
        "name": "Admissions Lead Tracker",
        "description": "First-party admissions pipeline and lead management.",
        "version": "1.0",
        "manifest": {"scopes": ["admissions"], "widgets": [], "wedge_ids": [1, 17, 38]},
    },
    {
        "slug": "billing-fees-pack",
        "name": "Billing & Fees Pack",
        "description": "First-party fee schedules, payment plans, and collections.",
        "version": "1.0",
        "manifest": {"scopes": ["finance"], "widgets": [], "wedge_ids": [1, 15, 32, 36]},
    },
    {
        "slug": "parent-engagement-pack",
        "name": "Parent Engagement Pack",
        "description": "First-party parent portal, notices, and consent workflows.",
        "version": "1.0",
        "manifest": {"scopes": ["communication"], "widgets": [], "wedge_ids": [1, 19, 35]},
    },
    {
        "slug": "analytics-insights-pack",
        "name": "Analytics & Insights Pack",
        "description": "First-party analytics and BI for academics and operations.",
        "version": "1.0",
        "manifest": {
            "scopes": ["analytics"],
            "widgets": [],
            "wedge_ids": [7, 8, 9, 10, 11, 12, 13, 31],
        },
    },
    {
        "slug": "attendance-intervention-pack",
        "name": "Attendance Intervention Pack",
        "description": "First-party attendance alerts and intervention workflows.",
        "version": "1.0",
        "manifest": {
            "scopes": ["attendance", "workflow"],
            "widgets": [],
            "wedge_ids": [23, 25, 30, 31, 40],
        },
    },
    {
        "slug": "grade-publishing-pack",
        "name": "Grade Publishing Pack",
        "description": "First-party grade approval and publishing workflows.",
        "version": "1.0",
        "manifest": {"scopes": ["evals"], "widgets": [], "wedge_ids": [2, 29, 31]},
    },
    {
        "slug": "compliance-audit-pack",
        "name": "Compliance & Audit Pack",
        "description": "First-party compliance reporting and audit trails.",
        "version": "1.0",
        "manifest": {
            "scopes": ["compliance"],
            "widgets": [],
            "wedge_ids": [4, 9, 14, 20, 42],
        },
    },
    {
        "slug": "ai-skills-pack",
        "name": "AI Skills Pack",
        "description": "First-party AI-assisted workflows and recommendations.",
        "version": "1.0",
        "manifest": {"scopes": ["ai"], "widgets": [], "wedge_ids": [31, 34, 37]},
    },
    {
        "slug": "reporting-export-pack",
        "name": "Reporting & Export Pack",
        "description": "First-party report builder and data export.",
        "version": "1.0",
        "manifest": {"scopes": ["reports"], "widgets": [], "wedge_ids": [1, 3, 20, 31]},
    },
    {
        "slug": "portal-themes-pack",
        "name": "Portal Themes Pack",
        "description": "First-party portal and marketing theme templates.",
        "version": "1.0",
        "manifest": {"scopes": ["brand"], "widgets": [], "wedge_ids": [1, 17, 18]},
    },
    {
        "slug": "onboarding-wizard-pack",
        "name": "Onboarding Wizard Pack",
        "description": "First-party school and tenant onboarding flows.",
        "version": "1.0",
        "manifest": {"scopes": ["setup"], "widgets": [], "wedge_ids": [1]},
    },
    {
        "slug": "api-webhooks-pack",
        "name": "API & Webhooks Pack",
        "description": "First-party API and webhook integration tools.",
        "version": "1.0",
        "manifest": {"scopes": ["integrations"], "widgets": [], "wedge_ids": [4, 44, 45]},
    },
    {
        "slug": "student-360-pack",
        "name": "Student 360 Pack",
        "description": "First-party holistic student view and intervention dashboard.",
        "version": "1.0",
        "manifest": {
            "scopes": ["academics", "people"],
            "widgets": [],
            "wedge_ids": [1, 6, 31, 43],
        },
    },
    # === 2026-05-14 wave NS-3 expansion: messaging / payments / SIS+LMS bridges / verticals ===
    {
        "slug": "messaging-sms-gateway",
        "name": "Messaging — SMS gateway",
        "description": "Send SMS via Twilio / Africa's Talking / Termii. Per-tenant credentials + delivery audit.",
        "version": "1.0",
        "manifest": {
            "scopes": ["communication", "integrations"],
            "widgets": [],
            "wedge_ids": [15, 24, 25, 44],
        },
    },
    {
        "slug": "messaging-whatsapp-broadcast",
        "name": "Messaging — WhatsApp Business broadcast",
        "description": "Approved-template broadcasts via WhatsApp Business API. Opt-in workflow + DPA.",
        "version": "1.0",
        "manifest": {
            "scopes": ["communication", "integrations"],
            "widgets": [],
            "wedge_ids": [15, 24, 25, 44],
        },
    },
    {
        "slug": "messaging-email-deliverability-pack",
        "name": "Messaging — Email deliverability pack",
        "description": "Per-tenant SPF/DKIM/DMARC config + bounce-rate dashboard. SES / Postmark / Mailgun adapters.",
        "version": "1.0",
        "manifest": {
            "scopes": ["communication", "integrations"],
            "widgets": [],
            "wedge_ids": [15, 25, 44],
        },
    },
    {
        "slug": "payments-stripe-connect",
        "name": "Payments — Stripe Connect",
        "description": "Tenant-billed Stripe Connect onboarding + revenue share for marketplace app sellers.",
        "version": "1.0",
        "manifest": {
            "scopes": ["finance", "integrations"],
            "widgets": [],
            "wedge_ids": [15, 32, 36, 44],
        },
    },
    {
        "slug": "payments-flutterwave-momo",
        "name": "Payments — Flutterwave / Mobile Money",
        "description": "MoMo, MTN, Orange, M-Pesa wallets via Flutterwave. West / East Africa optimized.",
        "version": "1.0",
        "manifest": {
            "scopes": ["finance", "integrations"],
            "widgets": [],
            "wedge_ids": [15, 32, 36],
        },
    },
    {
        "slug": "payments-paystack",
        "name": "Payments — Paystack",
        "description": "Paystack gateway for Nigeria / Ghana / Kenya / SA. Direct debit + recurring + invoice links.",
        "version": "1.0",
        "manifest": {
            "scopes": ["finance", "integrations"],
            "widgets": [],
            "wedge_ids": [15, 32, 36],
        },
    },
    {
        "slug": "payments-razorpay",
        "name": "Payments — Razorpay (India)",
        "description": "Razorpay UPI / NetBanking / cards for India. Sub-merchant onboarding.",
        "version": "1.0",
        "manifest": {
            "scopes": ["finance", "integrations"],
            "widgets": [],
            "wedge_ids": [15, 32, 36],
        },
    },
    {
        "slug": "sis-bridge-powerschool",
        "name": "SIS bridge — PowerSchool",
        "description": "Bidirectional roster / grade sync with PowerSchool. OneRoster v1.2 compatible.",
        "version": "1.0",
        "manifest": {
            "scopes": ["migration_import", "integrations"],
            "widgets": [],
            "wedge_ids": [1, 4, 44],
        },
    },
    {
        "slug": "sis-bridge-clever",
        "name": "SIS bridge — Clever",
        "description": "Clever rostering: SSO + roster sync + SAML JIT provisioning.",
        "version": "1.0",
        "manifest": {
            "scopes": ["identity", "integrations"],
            "widgets": [],
            "wedge_ids": [1, 2, 44, 45],
        },
    },
    {
        "slug": "sis-bridge-classlink",
        "name": "SIS bridge — ClassLink",
        "description": "ClassLink rostering + SSO + OneRoster sync.",
        "version": "1.0",
        "manifest": {
            "scopes": ["identity", "integrations"],
            "widgets": [],
            "wedge_ids": [1, 2, 44, 45],
        },
    },
    {
        "slug": "sis-bridge-oneroster-v1p2",
        "name": "SIS bridge — OneRoster v1.2",
        "description": "Generic OneRoster 1.2 producer + consumer. REST + bulk CSV.",
        "version": "1.0",
        "manifest": {
            "scopes": ["migration_import", "integrations"],
            "widgets": [],
            "wedge_ids": [1, 4, 44],
        },
    },
    {
        "slug": "lms-bridge-canvas",
        "name": "LMS bridge — Canvas",
        "description": "Canvas LTI 1.3 + Names & Roles + Assignment & Grades passback.",
        "version": "1.0",
        "manifest": {
            "scopes": ["academics", "integrations"],
            "widgets": [],
            "wedge_ids": [4, 26, 44],
        },
    },
    {
        "slug": "lms-bridge-google-classroom",
        "name": "LMS bridge — Google Classroom",
        "description": "Google Classroom course + roster + grade sync via Google Workspace for Education.",
        "version": "1.0",
        "manifest": {
            "scopes": ["academics", "integrations"],
            "widgets": [],
            "wedge_ids": [4, 26, 44],
        },
    },
    {
        "slug": "lms-bridge-microsoft-teams",
        "name": "LMS bridge — Microsoft Teams for Education",
        "description": "MS Teams class teams + assignments + grade passback via Graph API.",
        "version": "1.0",
        "manifest": {
            "scopes": ["academics", "integrations"],
            "widgets": [],
            "wedge_ids": [4, 26, 44],
        },
    },
    {
        "slug": "timetable-scheduling-pro",
        "name": "Timetable — Master scheduling Pro",
        "description": "Constraint-based master timetable + room booking + teacher load balancing.",
        "version": "1.0",
        "manifest": {
            "scopes": ["academics", "workflow"],
            "widgets": [],
            "wedge_ids": [4, 14, 16, 21, 22],
        },
    },
    {
        "slug": "library-asset-tracker",
        "name": "Library & asset tracker",
        "description": "Library checkout + barcode scan + asset depreciation + lost-item workflow.",
        "version": "1.0",
        "manifest": {
            "scopes": ["academics", "finance"],
            "widgets": [],
            "wedge_ids": [4, 32, 33],
        },
    },
    {
        "slug": "cafeteria-meal-plans",
        "name": "Cafeteria & meal plans",
        "description": "Meal plan subscriptions, allergen registry, daily POS integration.",
        "version": "1.0",
        "manifest": {
            "scopes": ["finance", "academics"],
            "widgets": [],
            "wedge_ids": [15, 32, 33],
        },
    },
    {
        "slug": "medical-clinic-records",
        "name": "Medical / clinic records",
        "description": "School nurse visit log + immunization registry + medication consent (HIPAA-aware schema).",
        "version": "1.0",
        "manifest": {
            "scopes": ["academics", "compliance"],
            "widgets": [],
            "wedge_ids": [6, 20, 43],
        },
    },
    {
        "slug": "boarding-house-management",
        "name": "Boarding house / dorm management",
        "description": "Dorm assignment + curfew tracking + visitor logs + parent permissions.",
        "version": "1.0",
        "manifest": {
            "scopes": ["academics", "communication"],
            "widgets": [],
            "wedge_ids": [6, 19, 33, 43],
        },
    },
    {
        "slug": "transport-route-optimizer",
        "name": "Transport route optimizer",
        "description": "Daily bus-route optimization with student stop assignments and GPS handoff.",
        "version": "1.0",
        "manifest": {
            "scopes": ["transport", "workflow"],
            "widgets": [],
            "wedge_ids": [14, 16, 33],
        },
    },
    # === 2026-05-14 wave NS-4: deep expansion to ~70 apps ===
    # Communication channels
    {"slug": "messaging-voice-broadcast", "name": "Messaging — Voice broadcast", "description": "IVR / voice-call broadcasts via Twilio / Vonage / Africa's Talking voice. Per-channel rate-limit + opt-in audit.", "version": "1.0", "manifest": {"scopes": ["messaging:write", "communication"], "widgets": [], "wedge_ids": [15, 24, 25]}},
    {"slug": "messaging-push-notifications", "name": "Messaging — Push notifications", "description": "FCM + APNs push to RunMyCampus mobile apps. Topic + per-user targeting.", "version": "1.0", "manifest": {"scopes": ["messaging:write", "communication"], "widgets": [], "wedge_ids": [15, 25]}},
    {"slug": "messaging-emergency-alert-system", "name": "Messaging — Emergency alert system", "description": "Multi-channel emergency broadcast (SMS + voice + push + email + WhatsApp) with delivery audit and drill mode.", "version": "1.0", "manifest": {"scopes": ["messaging:write", "communication"], "widgets": [], "wedge_ids": [15, 25, 42]}},
    # SIS / LMS additions
    {"slug": "sis-bridge-skyward", "name": "SIS bridge — Skyward", "description": "Skyward SIS bridge with bidirectional roster + grade sync.", "version": "1.0", "manifest": {"scopes": ["rostering:read", "rostering:write", "integrations:configure"], "widgets": [], "wedge_ids": [1, 4, 44]}},
    {"slug": "sis-bridge-veracross", "name": "SIS bridge — Veracross", "description": "Veracross SIS bridge for independent schools.", "version": "1.0", "manifest": {"scopes": ["rostering:read", "rostering:write", "integrations:configure"], "widgets": [], "wedge_ids": [1, 4, 44]}},
    {"slug": "sis-bridge-blackbaud-rene", "name": "SIS bridge — Blackbaud Education Management", "description": "Blackbaud Education Management (Re-Engage) bidirectional bridge.", "version": "1.0", "manifest": {"scopes": ["rostering:read", "rostering:write", "integrations:configure"], "widgets": [], "wedge_ids": [1, 4, 44]}},
    {"slug": "lms-bridge-moodle", "name": "LMS bridge — Moodle", "description": "Moodle LTI 1.3 + REST adapter for grade and course sync.", "version": "1.0", "manifest": {"scopes": ["lms:read", "lms:write", "integrations:configure"], "widgets": [], "wedge_ids": [4, 26, 44]}},
    {"slug": "lms-bridge-schoology", "name": "LMS bridge — Schoology", "description": "Schoology LMS bridge with assignment + grade passback.", "version": "1.0", "manifest": {"scopes": ["lms:read", "lms:write", "integrations:configure"], "widgets": [], "wedge_ids": [4, 26, 44]}},
    # Identity / SSO
    {"slug": "identity-google-sso", "name": "Identity — Google Workspace SSO", "description": "Google Workspace for Education SSO + JIT provisioning.", "version": "1.0", "manifest": {"scopes": ["identity:read", "identity:provision"], "widgets": [], "wedge_ids": [2, 44, 45]}},
    {"slug": "identity-azure-ad-sso", "name": "Identity — Microsoft Entra (Azure AD) SSO", "description": "Entra ID OIDC + SAML SSO with group-based role mapping.", "version": "1.0", "manifest": {"scopes": ["identity:read", "identity:provision"], "widgets": [], "wedge_ids": [2, 44, 45]}},
    {"slug": "identity-okta-sso", "name": "Identity — Okta SSO", "description": "Okta OIDC / SAML SSO + SCIM provisioning.", "version": "1.0", "manifest": {"scopes": ["identity:read", "identity:provision"], "widgets": [], "wedge_ids": [2, 44, 45]}},
    # Specialty / niche tools
    {"slug": "specialty-music-program", "name": "Specialty — Music Program", "description": "Instrument inventory, lesson schedules, recital workflow.", "version": "1.0", "manifest": {"scopes": ["academics"], "widgets": [], "wedge_ids": [4, 26]}},
    {"slug": "specialty-athletics-eligibility", "name": "Specialty — Athletics Eligibility", "description": "Student-athlete eligibility tracker (academics + attendance + clearance).", "version": "1.0", "manifest": {"scopes": ["academics", "compliance"], "widgets": [], "wedge_ids": [6, 20, 31]}},
    {"slug": "specialty-extracurricular-clubs", "name": "Specialty — Extracurricular Clubs", "description": "Club roster + meetings + permission slips.", "version": "1.0", "manifest": {"scopes": ["academics", "communication"], "widgets": [], "wedge_ids": [4, 25]}},
    {"slug": "specialty-special-education-iep", "name": "Specialty — Special Education / IEP", "description": "IEP plan authoring, accommodation tracking, parent sign-off.", "version": "1.0", "manifest": {"scopes": ["academics", "compliance", "medical:read"], "widgets": [], "wedge_ids": [4, 20, 31, 43]}},
    {"slug": "specialty-pastoral-care", "name": "Specialty — Pastoral / Counseling Care", "description": "Counselor caseload + intervention notes + parent meeting log.", "version": "1.0", "manifest": {"scopes": ["academics", "communication"], "widgets": [], "wedge_ids": [4, 25, 31, 43]}},
    {"slug": "specialty-after-school-program", "name": "Specialty — After-school Program", "description": "After-school program enrollment + attendance + parent pickup.", "version": "1.0", "manifest": {"scopes": ["academics", "finance"], "widgets": [], "wedge_ids": [15, 25, 33]}},
    # Alumni / Development
    {"slug": "alumni-engagement-pack", "name": "Alumni — Engagement Pack", "description": "Alumni directory + event RSVP + outreach campaigns.", "version": "1.0", "manifest": {"scopes": ["communication", "people"], "widgets": [], "wedge_ids": [25, 38]}},
    {"slug": "alumni-development-fundraising", "name": "Alumni — Development / Fundraising", "description": "Donation pipeline + pledge tracking + receipts.", "version": "1.0", "manifest": {"scopes": ["finance", "communication"], "widgets": [], "wedge_ids": [15, 32, 38]}},
    # Vendor / Procurement
    {"slug": "procurement-vendor-management", "name": "Procurement — Vendor Management", "description": "Vendor catalog + PO workflow + invoice matching.", "version": "1.0", "manifest": {"scopes": ["finance", "workflow"], "widgets": [], "wedge_ids": [15, 32, 36]}},
    # Backup / DR
    {"slug": "backup-disaster-recovery", "name": "Backup & Disaster Recovery", "description": "Per-tenant backup snapshot + restore wizard + DR drill scheduler.", "version": "1.0", "manifest": {"scopes": ["compliance", "integrations:configure"], "widgets": [], "wedge_ids": [20, 42, 44], "required_commercial_tier": "enterprise"}},
    # Hardware / IoT
    {"slug": "iot-biometric-attendance", "name": "IoT — Biometric Attendance", "description": "Fingerprint / RFID device adapter for attendance capture.", "version": "1.0", "manifest": {"scopes": ["attendance:write", "integrations:configure"], "widgets": [], "wedge_ids": [23, 33, 44]}},
    {"slug": "iot-rfid-asset-tracking", "name": "IoT — RFID Asset Tracking", "description": "RFID asset gates + loss-prevention alerts.", "version": "1.0", "manifest": {"scopes": ["library:write", "compliance"], "widgets": [], "wedge_ids": [33, 44]}},
    # Country-bundle starter packs
    {"slug": "country-bundle-nigeria", "name": "Country bundle — Nigeria", "description": "Nigeria starter: WAEC alignment, Naira currency, mobile-first parent portal.", "version": "1.0", "manifest": {"scopes": ["setup"], "widgets": [], "wedge_ids": [1, 17]}},
    {"slug": "country-bundle-kenya", "name": "Country bundle — Kenya", "description": "Kenya starter: KCSE alignment, M-Pesa via Flutterwave, SMS-first parent comms.", "version": "1.0", "manifest": {"scopes": ["setup"], "widgets": [], "wedge_ids": [1, 17]}},
    {"slug": "country-bundle-india", "name": "Country bundle — India", "description": "India starter: CBSE alignment, Razorpay UPI, regional language packs (Hindi + Tamil + Bengali).", "version": "1.0", "manifest": {"scopes": ["setup"], "widgets": [], "wedge_ids": [1, 17]}},
]


class Command(BaseCommand):
    help = "Seed first-party Marketplace apps and approved listings so App catalog is not empty. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write("Dry run: no changes will be written.")

        # Publisher for first-party apps
        publisher, pub_created = PublisherOrganization.objects.get_or_create(
            slug="runmycampus-first-party",
            defaults={
                "name": "RunMyCampus First-Party",
                "legal_name": "RunMyCampus First-Party",
                "verification_status": PublisherOrganization.VerificationStatus.VERIFIED,
            },
        )
        if pub_created and not dry_run:
            self.stdout.write(
                self.style.SUCCESS("Created publisher: RunMyCampus First-Party.")
            )
        elif (
            dry_run
            and not PublisherOrganization.objects.filter(
                slug="runmycampus-first-party"
            ).exists()
        ):
            self.stdout.write("Would create publisher: RunMyCampus First-Party.")

        created_apps = 0
        created_listings = 0
        for app_def in FIRST_PARTY_APPS:
            slug = app_def["slug"]
            if dry_run:
                if not MarketplaceApp.objects.filter(slug=slug).exists():
                    self.stdout.write(f"Would create app: {app_def['name']} ({slug})")
                    created_apps += 1
                app = MarketplaceApp.objects.filter(slug=slug).first()
                if app and not getattr(app, "listing", None):
                    self.stdout.write(f"Would create approved listing for: {slug}")
                    created_listings += 1
                continue

            manifest = dict(app_def.get("manifest") or {})
            prev = MarketplaceApp.objects.filter(slug=slug).first()
            if prev and isinstance(prev.manifest, dict):
                manifest = {**prev.manifest, **manifest}

            app, app_created = MarketplaceApp.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": app_def["name"],
                    "description": app_def.get("description", ""),
                    "kind": MarketplaceApp.AppKind.FIRST_PARTY,
                    "version": app_def.get("version", "1.0"),
                    "manifest": manifest,
                    "is_active": True,
                    "publisher": publisher,
                    # Explicit free catalog: MarketplaceApp.clean requires this when pricing_model is FREE.
                    "pricing_model": MarketplaceApp.PricingModel.FREE,
                    "is_intentionally_free": True,
                },
            )
            if app_created:
                created_apps += 1

            listing, list_created = MarketplaceListing.objects.get_or_create(
                app=app,
                defaults={
                    "publisher": publisher,
                    "short_description": (app.description or "")[:255],
                    "status": MarketplaceListing.Status.APPROVED,
                    "security_review_status": MarketplaceListing.ReviewStatus.NOT_REQUIRED,
                    "certification_status": MarketplaceListing.ReviewStatus.NOT_REQUIRED,
                    "kill_switch_active": False,
                    "approved_at": timezone.now(),
                },
            )
            if (
                not list_created
                and listing.status != MarketplaceListing.Status.APPROVED
            ):
                listing.status = MarketplaceListing.Status.APPROVED
                listing.kill_switch_active = False
                listing.save(
                    update_fields=["status", "kill_switch_active", "updated_at"]
                )
                created_listings += 1
            elif list_created:
                created_listings += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Marketplace apps: {len(FIRST_PARTY_APPS)} ensured ({created_apps} created). "
                f"Listings approved: {created_listings}."
            )
        )
        if not dry_run:
            _phase9_enrich_catalog(self.stdout, self.style)
