"""
Build PackageVersion.payload_sections for legacy seed_first_party_apps (27 package IDs).

Distinct from marketplace catalog slugs (73 rows via seed_marketplace_catalog_packages).
These IDs satisfy MARKETPLACE_SEED_TARGETS first_party_apps inventory minimums.
"""

from __future__ import annotations

from typing import Any

# Canonical list — imported by seed_first_party_apps management command.
FIRST_PARTY_APP_DEFINITIONS: list[dict[str, str]] = [
    {
        "package_id": "admissions-core",
        "version": "1.0",
        "changelog_summary": "Admissions application and review.",
    },
    {
        "package_id": "admissions-document-verify",
        "version": "1.0",
        "changelog_summary": "Document verification workflow.",
    },
    {
        "package_id": "finance-invoicing",
        "version": "1.0",
        "changelog_summary": "Fee and invoice management.",
    },
    {
        "package_id": "finance-refunds",
        "version": "1.0",
        "changelog_summary": "Refund approval workflow.",
    },
    {
        "package_id": "gradebook-standard",
        "version": "1.0",
        "changelog_summary": "Grade entry and publish.",
    },
    {
        "package_id": "gradebook-appeals",
        "version": "1.0",
        "changelog_summary": "Grade appeal workflow.",
    },
    {
        "package_id": "attendance-basic",
        "version": "1.0",
        "changelog_summary": "Daily attendance and escalation.",
    },
    {
        "package_id": "attendance-truancy",
        "version": "1.0",
        "changelog_summary": "Truancy alerts and reporting.",
    },
    {
        "package_id": "compliance-evidence",
        "version": "1.0",
        "changelog_summary": "Compliance evidence and audit.",
    },
    {
        "package_id": "hr-onboarding",
        "version": "1.0",
        "changelog_summary": "Staff onboarding checklist.",
    },
    {
        "package_id": "hr-leave",
        "version": "1.0",
        "changelog_summary": "Leave request and approval.",
    },
    {
        "package_id": "communications-broadcast",
        "version": "1.0",
        "changelog_summary": "Announcements and broadcast.",
    },
    {
        "package_id": "enrollment-reenroll",
        "version": "1.0",
        "changelog_summary": "Re-enrollment workflow.",
    },
    {
        "package_id": "enrollment-withdrawal",
        "version": "1.0",
        "changelog_summary": "Withdrawal and exit checklist.",
    },
    {
        "package_id": "discipline-incident",
        "version": "1.0",
        "changelog_summary": "Incident report and follow-up.",
    },
    {
        "package_id": "reporting-export",
        "version": "1.0",
        "changelog_summary": "Data export and delivery.",
    },
    {
        "package_id": "scheduler-bell",
        "version": "1.0",
        "changelog_summary": "Bell schedule and periods.",
    },
    {
        "package_id": "scheduler-rooms",
        "version": "1.0",
        "changelog_summary": "Room and resource scheduling.",
    },
    {
        "package_id": "parent-portal-basic",
        "version": "1.0",
        "changelog_summary": "Parent portal and progress.",
    },
    {
        "package_id": "parent-payments",
        "version": "1.0",
        "changelog_summary": "Parent fee and payment view.",
    },
    {
        "package_id": "teacher-gradebook",
        "version": "1.0",
        "changelog_summary": "Teacher gradebook and roster.",
    },
    {
        "package_id": "teacher-attendance",
        "version": "1.0",
        "changelog_summary": "Teacher attendance entry.",
    },
    {
        "package_id": "registrar-enrollment",
        "version": "1.0",
        "changelog_summary": "Registrar enrollment and sections.",
    },
    {
        "package_id": "counselor-caseload",
        "version": "1.0",
        "changelog_summary": "Counselor caseload and notes.",
    },
    {
        "package_id": "nurse-health-log",
        "version": "1.0",
        "changelog_summary": "Health log and medication.",
    },
    {
        "package_id": "admin-dashboard-exec",
        "version": "1.0",
        "changelog_summary": "Executive dashboard and KPIs.",
    },
    {
        "package_id": "api-public-readonly",
        "version": "1.0",
        "changelog_summary": "Public read-only API pack.",
    },
]

_SECTION_BY_PREFIX: list[tuple[str, str]] = [
    ("admissions-", "blueprint"),
    ("finance-", "workflow"),
    ("gradebook-", "dashboard"),
    ("attendance-", "workflow"),
    ("compliance-", "policy"),
    ("hr-", "workflow"),
    ("communications-", "experience_pack"),
    ("enrollment-", "workflow"),
    ("discipline-", "workflow"),
    ("reporting-", "dashboard"),
    ("scheduler-", "experience_pack"),
    ("parent-", "experience_pack"),
    ("teacher-", "dashboard"),
    ("registrar-", "workflow"),
    ("counselor-", "experience_pack"),
    ("nurse-", "experience_pack"),
    ("admin-dashboard-", "dashboard"),
    ("api-public-", "experience_pack"),
]

_DOMAIN_BY_PREFIX: list[tuple[str, str]] = [
    ("admissions-", "admissions"),
    ("finance-", "finance"),
    ("gradebook-", "academics"),
    ("attendance-", "attendance"),
    ("compliance-", "compliance"),
    ("hr-", "people"),
    ("communications-", "communication"),
    ("enrollment-", "enrollment"),
    ("discipline-", "discipline"),
    ("reporting-", "reporting"),
    ("scheduler-", "scheduling"),
    ("parent-", "parent_portal"),
    ("teacher-", "teacher"),
    ("registrar-", "registrar"),
    ("counselor-", "counseling"),
    ("nurse-", "health"),
    ("admin-dashboard-", "analytics"),
    ("api-public-", "api"),
]


def _match_prefix(package_id: str, table: list[tuple[str, str]], default: str) -> str:
    pid = (package_id or "").strip().lower()
    for prefix, value in table:
        if pid.startswith(prefix):
            return value
    return default


def _primary_section_for_package_id(package_id: str) -> str:
    return _match_prefix(package_id, _SECTION_BY_PREFIX, "experience_pack")


def _domain_for_package_id(package_id: str) -> str:
    return _match_prefix(package_id, _DOMAIN_BY_PREFIX, "platform")


def build_first_party_package_payload(
    *,
    package_id: str,
    version: str,
    changelog_summary: str = "",
) -> dict[str, Any]:
    """Return non-empty payload_sections for a legacy first-party package_id."""
    pid = (package_id or "").strip()
    section = _primary_section_for_package_id(pid)
    domain = _domain_for_package_id(pid)
    surface = pid.replace("-", "_")
    body: dict[str, Any] = {
        "package_id": pid,
        "catalog_version": version,
        "domain": domain,
        "description": (changelog_summary or "")[:500],
        "source": "first_party_app_seed",
        "entity_codes": [domain],
    }
    if section == "workflow":
        body["pack"] = surface
        body["trigger_events"] = ["package_applied", "app_installed"]
    elif section == "dashboard":
        body["surface"] = surface
        body["widget_ids"] = [f"rmc-widget-{pid}"]
    elif section == "policy":
        body["bundle"] = surface
    elif section == "blueprint":
        body["family"] = surface
    elif section == "experience_pack":
        body["experience"] = surface
        body["capabilities"] = [domain]
    return {section: body}


def first_party_package_rows(
    definitions: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Expand legacy definitions into PackageVersion upsert rows."""
    rows: list[dict[str, Any]] = []
    for item in definitions or FIRST_PARTY_APP_DEFINITIONS:
        package_id = str(item.get("package_id") or "").strip()
        if not package_id:
            continue
        version = str(item.get("version") or "1.0").strip()
        changelog = str(item.get("changelog_summary") or "")
        rows.append(
            {
                "package_id": package_id,
                "version": version,
                "payload_sections": build_first_party_package_payload(
                    package_id=package_id,
                    version=version,
                    changelog_summary=changelog,
                ),
                "changelog_summary": changelog[:500],
                "compatibility": {
                    "min_platform": "2025.03",
                    "legacy_first_party": True,
                },
            }
        )
    return rows
