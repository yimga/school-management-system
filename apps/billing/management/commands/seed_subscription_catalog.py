from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import BillingPromotion
from apps.siteconfig.models_platform_catalog import Plan, PlanAddon


PLAN_CATALOG = (
    {
        "slug": "free-starter",
        "name": "Free Starter",
        "base_price": "0.00",
        # Deliberately UNCAPPED on size. This is the plan every new tenant binds
        # to (is_default), so any number here is a fuse on the whole school: a
        # school's size is fixed by its building, so it cannot grow into a plan
        # the way a store grows sales -- a cap either locks it out on day one or
        # never binds. At the previous 50 students / 5 staff, Free was a demo,
        # not a product: real schools run 300-1000 students and 20-40 staff.
        # Free core is monetised by the share of fees collected through the
        # platform, not by the school's size, so the free tier is bounded by
        # FEATURES (below) instead.
        "max_students": None,
        "max_staff": None,
        "is_default": True,
        "features": ["attendance", "student_records", "parent_portal", "basic_reports"],
    },
    {
        "slug": "micro-school",
        "name": "Micro School",
        "base_price": "19.00",
        "max_students": 120,
        "max_staff": 12,
        "features": ["attendance", "student_records", "parent_portal", "finance_basic", "report_cards"],
    },
    {
        "slug": "small-school",
        "name": "Small School",
        "base_price": "49.00",
        "max_students": 350,
        "max_staff": 35,
        "features": ["attendance", "student_records", "parent_portal", "finance_basic", "communication", "report_cards"],
    },
    {
        "slug": "growing-school",
        "name": "Growing School",
        "base_price": "99.00",
        "max_students": 900,
        "max_staff": 90,
        "features": ["attendance", "student_records", "parent_portal", "finance", "communication", "admissions", "analytics_basic"],
    },
    {
        "slug": "professional-school",
        "name": "Professional School",
        "base_price": "249.00",
        "max_students": 2500,
        "max_staff": 250,
        "features": ["attendance", "student_records", "parent_portal", "finance", "communication", "admissions", "analytics", "lms", "api_basic"],
    },
    {
        "slug": "multi-campus",
        "name": "Multi-Campus",
        "base_price": "599.00",
        "max_students": 7500,
        "max_staff": 750,
        "features": ["multi_campus", "finance", "analytics", "lms", "api_basic", "workflow_packs", "brand_controls"],
    },
    {
        "slug": "enterprise-network",
        "name": "Enterprise School Network",
        "base_price": "1499.00",
        "max_students": None,
        "max_staff": None,
        "features": ["multi_campus", "sso", "advanced_analytics", "api_advanced", "migration_cloud", "priority_support"],
    },
    {
        "slug": "district-ministry",
        "name": "District / Ministry",
        "base_price": "0.00",
        "billing_model": Plan.BillingModel.TIERED,
        "tier_rules": [
            {"max": 10000, "price": 2500},
            {"max": 50000, "price": 8500},
            {"max": 0, "price": 18000},
        ],
        "max_students": None,
        "max_staff": None,
        "features": ["district_reporting", "emis", "policy_bundles", "sso", "api_advanced", "data_residency"],
    },
    {
        "slug": "ngo-low-resource",
        "name": "NGO / Low-Resource Region",
        "base_price": "9.00",
        "max_students": 500,
        "max_staff": 50,
        "features": ["attendance", "student_records", "offline_sync", "parent_portal", "basic_reports"],
    },
    {
        "slug": "developer-partner",
        "name": "Developer / Partner",
        "base_price": "49.00",
        "max_students": 100,
        "max_staff": 10,
        "features": ["api_basic", "sandbox", "webhooks", "marketplace_publisher"],
    },
    {
        "slug": "white-label",
        "name": "White Label",
        "base_price": "999.00",
        "max_students": None,
        "max_staff": None,
        "features": ["custom_branding", "custom_domain", "marketplace_private", "priority_support"],
    },
    {
        "slug": "sovereign-self-hosted",
        "name": "Sovereign / Self-Hosted",
        "base_price": "0.00",
        "billing_model": Plan.BillingModel.TIERED,
        "tier_rules": [
            {"max": 5000, "price": 1200},
            {"max": 25000, "price": 4500},
            {"max": 0, "price": 12000},
        ],
        "max_students": None,
        "max_staff": None,
        "features": ["self_hosted", "data_residency", "offline_sync", "api_advanced", "support_sla"],
    },
)

PLAN_ENRICHMENT = {
    "free-starter": {
        "display_order": 10,
        "audience": "Small pilots and new schools",
        "tenant_summary": "Start with core records, attendance, parent access, and basic reports.",
        "cycles": ["monthly", "annual"],
        "payments": ["card", "mobile_money"],
        "usage": {"students": 50, "staff": 5, "storage_gb": 2, "messages_month": 250},
        "support": {"tier": "community", "onboarding": "self_guided"},
    },
    "micro-school": {
        "display_order": 20,
        "audience": "1-120 students",
        "tenant_summary": "Affordable operations for micro-schools that need fees, reports, and family access.",
        "cycles": ["monthly", "annual", "school_year"],
        "payments": ["card", "bank_transfer", "mobile_money", "invoice"],
        "usage": {"students": 120, "staff": 12, "storage_gb": 10, "messages_month": 1500},
        "support": {"tier": "standard", "onboarding": "checklist"},
    },
    "small-school": {
        "display_order": 30,
        "audience": "121-350 students",
        "tenant_summary": "A simple full-school package for admissions, communication, fees, and reports.",
        "cycles": ["monthly", "annual", "school_year"],
        "payments": ["card", "bank_transfer", "mobile_money", "invoice"],
        "usage": {"students": 350, "staff": 35, "storage_gb": 25, "messages_month": 5000},
        "support": {"tier": "standard", "onboarding": "guided"},
    },
    "growing-school": {
        "display_order": 40,
        "audience": "351-900 students",
        "tenant_summary": "Scale daily school operations with admissions, finance, communication, and analytics.",
        "cycles": ["monthly", "annual", "school_year"],
        "payments": ["card", "bank_transfer", "mobile_money", "invoice", "purchase_order"],
        "usage": {"students": 900, "staff": 90, "storage_gb": 75, "messages_month": 15000},
        "support": {"tier": "priority", "onboarding": "guided"},
    },
    "professional-school": {
        "display_order": 50,
        "audience": "901-2,500 students",
        "tenant_summary": "Advanced academics, LMS, API access, analytics, and stronger support for mature schools.",
        "cycles": ["monthly", "annual", "school_year", "custom_contract"],
        "payments": ["card", "bank_transfer", "invoice", "purchase_order"],
        "usage": {"students": 2500, "staff": 250, "storage_gb": 250, "messages_month": 50000},
        "support": {"tier": "priority", "onboarding": "implementation_call"},
    },
    "multi-campus": {
        "display_order": 60,
        "audience": "School groups and campuses",
        "tenant_summary": "Manage multiple campuses, brand controls, workflow packs, and roll-up analytics.",
        "cycles": ["annual", "school_year", "custom_contract"],
        "payments": ["bank_transfer", "invoice", "purchase_order"],
        "usage": {"students": 7500, "staff": 750, "storage_gb": 1000, "messages_month": 150000},
        "support": {"tier": "premium", "onboarding": "project_plan", "success_manager": True},
    },
    "enterprise-network": {
        "display_order": 70,
        "audience": "Large networks",
        "tenant_summary": "Enterprise controls for SSO, advanced APIs, migration, analytics, and SLA-backed support.",
        "cycles": ["annual", "multi_year", "custom_contract"],
        "payments": ["bank_transfer", "invoice", "purchase_order"],
        "usage": {"students": "unlimited", "staff": "unlimited", "storage_gb": "contract", "api_calls_month": "contract"},
        "support": {"tier": "enterprise", "sla": "contract", "success_manager": True},
        "requires_quote": True,
    },
    "district-ministry": {
        "display_order": 80,
        "audience": "Districts, ministries, and public systems",
        "tenant_summary": "Policy reporting, EMIS-style data, data residency, and scale controls for public education.",
        "cycles": ["annual", "multi_year", "custom_contract"],
        "payments": ["bank_transfer", "invoice", "purchase_order"],
        "usage": {"students": "tiered", "staff": "tiered", "data_residency": "configurable"},
        "support": {"tier": "sovereign", "sla": "contract", "program_manager": True},
        "requires_quote": True,
    },
    "ngo-low-resource": {
        "display_order": 25,
        "audience": "NGOs and low-resource schools",
        "tenant_summary": "Low-cost access with offline sync, parent access, student records, and basic reporting.",
        "cycles": ["monthly", "annual", "school_year"],
        "payments": ["card", "bank_transfer", "mobile_money", "invoice"],
        "usage": {"students": 500, "staff": 50, "storage_gb": 20, "messages_month": 5000},
        "support": {"tier": "standard", "sponsorship_review": True},
    },
    "developer-partner": {
        "display_order": 90,
        "audience": "Partners and marketplace builders",
        "tenant_summary": "Sandbox, webhooks, API access, and marketplace publisher capabilities.",
        "cycles": ["monthly", "annual"],
        "payments": ["card", "bank_transfer", "invoice"],
        "usage": {"sandbox_tenants": 3, "api_calls_month": 100000},
        "support": {"tier": "developer"},
    },
    "white-label": {
        "display_order": 100,
        "audience": "Resellers and branded operators",
        "tenant_summary": "Custom brand, custom domain, private marketplace, and priority support.",
        "cycles": ["annual", "multi_year", "custom_contract"],
        "payments": ["bank_transfer", "invoice", "purchase_order"],
        "usage": {"brands": 1, "private_marketplace": True},
        "support": {"tier": "premium", "success_manager": True},
        "requires_quote": True,
    },
    "sovereign-self-hosted": {
        "display_order": 110,
        "audience": "Sovereign, offline, and self-hosted deployments",
        "tenant_summary": "Self-hosted or sovereign deployment for strict data residency and offline-first operations.",
        "cycles": ["annual", "multi_year", "custom_contract"],
        "payments": ["bank_transfer", "invoice", "purchase_order"],
        "usage": {"deployment": "self_hosted", "data_residency": "configurable"},
        "support": {"tier": "sovereign", "sla": "contract"},
        "requires_quote": True,
    },
}

ADDON_CATALOG = (
    ("advanced-analytics", "Advanced analytics", "59.00"),
    ("ai-assistant", "AI assistant", "79.00"),
    ("sms-pack", "SMS message pack", "25.00"),
    ("whatsapp-pack", "WhatsApp message pack", "35.00"),
    ("storage-pack", "Storage pack", "15.00"),
    ("custom-domain", "Custom domain", "19.00"),
    ("white-label-branding", "White-label branding", "199.00"),
    ("admissions", "Admissions module", "49.00"),
    ("hr-payroll", "HR / payroll", "69.00"),
    ("transport", "Transport module", "39.00"),
    ("library", "Library module", "29.00"),
    ("inventory", "Inventory module", "29.00"),
    ("hostel", "Hostel / dormitory", "39.00"),
    ("cafeteria", "Cafeteria module", "29.00"),
    ("lms", "Learning management", "89.00"),
    ("sso-saml", "SSO / SAML", "149.00"),
    ("premium-onboarding", "Premium onboarding", "499.00"),
    ("priority-support", "Priority support", "199.00"),
    ("compliance-pack", "Compliance package", "99.00"),
    ("offline-mobile", "Offline / mobile package", "59.00"),
)

ADDON_ENRICHMENT = {
    "advanced-analytics": ("Analytics", "Deeper dashboards, cohort analysis, and executive reporting.", "analytics"),
    "ai-assistant": ("AI", "AI support for drafting, search, summaries, and operational assistance.", "ai"),
    "sms-pack": ("Communication", "SMS bundle for parent, staff, and student notifications.", "communication"),
    "whatsapp-pack": ("Communication", "WhatsApp messaging bundle where supported by local providers.", "communication"),
    "storage-pack": ("Platform", "Extra document, media, and backup storage.", "storage"),
    "custom-domain": ("Brand", "Use a school-owned domain for tenant access.", "branding"),
    "white-label-branding": ("Brand", "Expanded reseller and institution branding controls.", "branding"),
    "admissions": ("Admissions", "Online applications, review workflow, and applicant conversion.", "admissions"),
    "hr-payroll": ("HR", "Staff records, HR workflow, and payroll preparation support.", "hr"),
    "transport": ("Operations", "Routes, vehicles, drivers, pickup tracking, and transport fees.", "operations"),
    "library": ("Academics", "Library inventory, circulation, and overdue tracking.", "academics"),
    "inventory": ("Operations", "Asset, inventory, issue, and stock tracking.", "operations"),
    "hostel": ("Residential", "Dormitory rooms, residents, allocation, and hostel fees.", "residential"),
    "cafeteria": ("Operations", "Meal plans, cafeteria sales, and food-service operations.", "operations"),
    "lms": ("Learning", "Courses, learning activities, resources, and online classroom support.", "learning"),
    "sso-saml": ("Security", "Single sign-on and SAML/OIDC identity integration.", "security"),
    "premium-onboarding": ("Services", "Implementation support, data setup, and launch planning.", "services"),
    "priority-support": ("Support", "Priority response and enhanced support coverage.", "support"),
    "compliance-pack": ("Compliance", "Policy, audit, and regional compliance workflow pack.", "compliance"),
    "offline-mobile": ("Mobile", "Offline and mobile-first operations for low-connectivity regions.", "mobile"),
}

PROMOTION_CATALOG = (
    {
        "code": "founder-first-year-50",
        "name": "Founder first-year 50%",
        "percent_off": "50.000",
        "scope": BillingPromotion.Scope.GLOBAL,
        "metadata": {"duration": "first_year", "strategic_use": "launch"},
    },
    {
        "code": "ngo-sponsorship-100",
        "name": "NGO sponsorship 100%",
        "percent_off": "100.000",
        "scope": BillingPromotion.Scope.PARTNER,
        "metadata": {"approval_required": True, "strategic_use": "sponsored_access"},
    },
    {
        "code": "emerging-market-30",
        "name": "Emerging market 30%",
        "percent_off": "30.000",
        "scope": BillingPromotion.Scope.REGION,
        "country_codes": ["CM", "NG", "KE", "UG", "GH", "IN", "PK", "BD"],
        "metadata": {"strategic_use": "regional_expansion"},
    },
)


class Command(BaseCommand):
    help = "Seed the broad RunMyCampus subscription plan, add-on, and promotion catalog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        summary = {"plans": 0, "addons": 0, "promotions": 0}

        for spec in PLAN_CATALOG:
            defaults = {
                "name": spec["name"],
                "base_price": Decimal(spec.get("base_price", "0.00")),
                "billing_model": spec.get("billing_model", Plan.BillingModel.FLAT),
                "tier_rules": spec.get("tier_rules", {}),
                "max_students": spec.get("max_students"),
                "max_staff": spec.get("max_staff"),
                "included_features": spec.get("features", []),
                "is_active": True,
                "is_default": bool(spec.get("is_default", False)),
            }
            enrichment = PLAN_ENRICHMENT.get(spec["slug"], {})
            defaults.update(
                {
                    "display_order": enrichment.get("display_order", 0),
                    "audience": enrichment.get("audience", ""),
                    "tenant_summary": enrichment.get("tenant_summary", ""),
                    "billing_cycle_options": enrichment.get(
                        "cycles", ["monthly", "annual"]
                    ),
                    "payment_method_options": enrichment.get(
                        "payments", ["card", "bank_transfer", "invoice"]
                    ),
                    "included_usage": enrichment.get("usage", {}),
                    "support_policy": enrichment.get("support", {}),
                    "tenant_visible": True,
                    "requires_quote": bool(enrichment.get("requires_quote", False)),
                    "configuration_schema": {
                        "regional_pricing": "country_profile_plus_sku_override",
                        "addons": "configurable",
                        "promotions": "grant_based",
                        "waivers": "operator_approved",
                    },
                }
            )
            if dry_run:
                self.stdout.write(f"[dry-run] plan {spec['slug']}: {defaults}")
            else:
                Plan.objects.update_or_create(slug=spec["slug"], defaults=defaults)
            summary["plans"] += 1

        for idx, (code, name, price) in enumerate(ADDON_CATALOG, start=1):
            category_label, description, category = ADDON_ENRICHMENT.get(
                code,
                ("General", "", "general"),
            )
            defaults = {
                "name": name,
                "description": description,
                "category": category,
                "price": Decimal(price),
                "billing_unit": (
                    PlanAddon.BillingUnit.ONE_TIME
                    if category == "services"
                    else PlanAddon.BillingUnit.PER_TENANT
                ),
                "included_in_plan_codes": [],
                "available_to_plan_codes": [],
                "configuration_schema": {
                    "category_label": category_label,
                    "regional_overrides": "optional",
                    "approval_required": category in {"security", "compliance", "services"},
                },
                "display_order": idx * 10,
                "tenant_visible": True,
                "is_active": True,
            }
            if dry_run:
                self.stdout.write(f"[dry-run] addon {code}: {defaults}")
            else:
                PlanAddon.objects.update_or_create(code=code, defaults=defaults)
            summary["addons"] += 1

        for spec in PROMOTION_CATALOG:
            defaults = {
                "name": spec["name"],
                "discount_type": BillingPromotion.DiscountType.PERCENT,
                "percent_off": Decimal(spec["percent_off"]),
                "fixed_amount": Decimal("0.00"),
                "scope": spec.get("scope", BillingPromotion.Scope.GLOBAL),
                "country_codes": spec.get("country_codes", []),
                "is_active": True,
                "metadata": spec.get("metadata", {}),
            }
            if dry_run:
                self.stdout.write(f"[dry-run] promotion {spec['code']}: {defaults}")
            else:
                BillingPromotion.objects.update_or_create(
                    code=spec["code"], defaults=defaults
                )
            summary["promotions"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Subscription catalog seed complete "
                f"(plans={summary['plans']}, addons={summary['addons']}, "
                f"promotions={summary['promotions']})."
            )
        )
