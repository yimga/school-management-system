"""
Map marketplace catalog slugs to legacy seed_first_party_apps package IDs.

Operators and inventory tooling expect admissions-core-style IDs on listings;
activate applies the legacy PackageVersion payload when a mapping exists.
"""

from __future__ import annotations

from apps.packages.first_party_package_payloads import FIRST_PARTY_APP_DEFINITIONS

LEGACY_PACKAGE_IDS: frozenset[str] = frozenset(
    item["package_id"] for item in FIRST_PARTY_APP_DEFINITIONS
)

# Catalog slug → legacy package_id (each legacy ID appears at least once).
CATALOG_SLUG_TO_LEGACY_PACKAGE_ID: dict[str, str] = {
    "admissions-lead-tracker": "admissions-core",
    "international-k12-core-starter": "admissions-document-verify",
    "billing-fees-pack": "finance-invoicing",
    "procurement-vendor-management": "finance-refunds",
    "grade-publishing-pack": "gradebook-standard",
    "ai-grading-assistant": "gradebook-appeals",
    "attendance-intervention-pack": "attendance-basic",
    "specialty-athletics-eligibility": "attendance-truancy",
    "compliance-export": "compliance-evidence",
    "compliance-audit-pack": "compliance-evidence",
    "onboarding-wizard-pack": "hr-onboarding",
    "district-pack": "hr-leave",
    "premium-communication-pack": "communications-broadcast",
    "messaging-sms-gateway": "communications-broadcast",
    "messaging-whatsapp-broadcast": "communications-broadcast",
    "private-school-pack": "enrollment-reenroll",
    "global-readiness-starter": "enrollment-withdrawal",
    "specialty-special-education-iep": "discipline-incident",
    "reporting-export-pack": "reporting-export",
    "timetable-scheduling-pro": "scheduler-bell",
    "transport-route-optimizer": "scheduler-rooms",
    "parent-engagement-pack": "parent-portal-basic",
    "payments-stripe-connect": "parent-payments",
    "ai-skills-pack": "teacher-gradebook",
    "specialty-after-school-program": "teacher-attendance",
    "enterprise-governance-console": "registrar-enrollment",
    "specialty-pastoral-care": "counselor-caseload",
    "medical-clinic-records": "nurse-health-log",
    "executive-insights": "admin-dashboard-exec",
    "advanced-analytics-pack": "admin-dashboard-exec",
    "analytics-insights-pack": "admin-dashboard-exec",
    "api-webhooks-pack": "api-public-readonly",
}


def resolve_legacy_package_id(slug: str) -> str | None:
    """Return legacy package_id for a catalog slug, if wired."""
    pid = CATALOG_SLUG_TO_LEGACY_PACKAGE_ID.get((slug or "").strip())
    if pid and pid in LEGACY_PACKAGE_IDS:
        return pid
    return None


def resolve_activate_package_id(slug: str, manifest: dict | None = None) -> str:
    """Package id used on activate (legacy when mapped, else manifest or slug)."""
    manifest = manifest if isinstance(manifest, dict) else {}
    explicit = str(manifest.get("package_id") or "").strip()
    if explicit and explicit in LEGACY_PACKAGE_IDS:
        return explicit
    legacy = resolve_legacy_package_id(slug)
    if legacy:
        return legacy
    if explicit:
        return explicit
    return (slug or "").strip()


def legacy_binding_validation_errors() -> list[str]:
    """All legacy IDs mapped + every mapping target has a seeded PackageVersion."""
    from apps.packages.models import PackageVersion

    errors: list[str] = []
    mapped_legacy = set(CATALOG_SLUG_TO_LEGACY_PACKAGE_ID.values())
    unmapped_legacy = sorted(LEGACY_PACKAGE_IDS - mapped_legacy)
    if unmapped_legacy:
        errors.append(f"legacy package IDs without catalog slug: {', '.join(unmapped_legacy)}")

    for slug, package_id in sorted(CATALOG_SLUG_TO_LEGACY_PACKAGE_ID.items()):
        if package_id not in LEGACY_PACKAGE_IDS:
            errors.append(f"{slug}: unknown legacy package_id {package_id!r}")
            continue
        pv = PackageVersion.objects.filter(package_id=package_id, version="1.0").first()
        if pv is None:
            errors.append(f"{slug}: missing PackageVersion for legacy {package_id}")
        elif not (pv.payload_sections or {}):
            errors.append(f"{slug}: empty payload on legacy {package_id}")

    return errors
