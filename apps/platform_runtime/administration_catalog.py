"""Administration and configuration surface catalog.

This module is intentionally data-first: the /configuration/ product surface is
a facade over existing RunMyCampus systems, not a new source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class SurfaceLink:
    label: str
    route_name: str = ""
    path: str = ""


@dataclass(frozen=True)
class ConfigurationModule:
    key: str
    title: str
    purpose: str
    owner: str
    scope: str
    status: str
    primary_action: str
    existing_route: SurfaceLink
    proof: SurfaceLink = field(default_factory=lambda: SurfaceLink("Audit proof", path="/docs/generated/route_surface_audit.json"))
    detail: str = ""


def resolve_surface_link(link: SurfaceLink) -> str:
    if link.route_name:
        try:
            return reverse(link.route_name)
        except NoReverseMatch:
            pass
    return link.path or "/super/"


def _link(label: str, route_name: str = "", path: str = "") -> SurfaceLink:
    return SurfaceLink(label=label, route_name=route_name, path=path)


CONFIGURATION_MODULES: tuple[ConfigurationModule, ...] = (
    ConfigurationModule(
        "blueprints",
        "Blueprint Marketplace",
        "Configure previewable school operating models with implementation, policy, workflow, dashboard, metadata, billing, and offline defaults.",
        "Platform configuration",
        "platform_only",
        "ready",
        "Open blueprint facade",
        _link("Super blueprint catalog", "super:blueprints_catalog"),
        _link("Blueprint foundation tests", path="/apps/platform_runtime/tests/test_blueprint_marketplace_foundations.py"),
        "Apply remains preview-first unless a governed package operation already exists.",
    ),
    ConfigurationModule(
        "app-catalog",
        "App Catalog",
        "Review platform apps, scopes, sandbox posture, billing truth, tenant install impact, and partner status.",
        "Marketplace governance",
        "both",
        "partial",
        "Open app catalog facade",
        _link("Marketplace app catalog", "super:app_catalog"),
        _link("Marketplace readiness tests", path="/apps/platform_runtime/tests/test_marketplace_catalog_minimums.py"),
        "External monetization remains external_required until settlement proof exists.",
    ),
    ConfigurationModule(
        "packages",
        "Package Rollout",
        "Coordinate modules, limits, support levels, API access, offline eligibility, downgrade behavior, rollout, and audit posture.",
        "Package operations",
        "platform_only",
        "ready",
        "Open package library",
        _link("Package rollout", "super:package_rollout"),
    ),
    ConfigurationModule(
        "workflow-packs",
        "Workflow Packs",
        "Govern triggers, conditions, actions, owners, escalations, simulation, deactivation, rollback, and kill-switch posture.",
        "Automation studio",
        "both",
        "ready",
        "Open workflow packs",
        _link("Super workflow packs", "super:workflow_packs_catalog"),
        _link("Low-click workflow tests", path="/apps/platform_runtime/tests/test_low_click_workflow_contracts.py"),
    ),
    ConfigurationModule(
        "dashboard-packs",
        "Dashboard Packs",
        "Configure role dashboards, widgets, metrics, risks, primary actions, permissions, density, mobile behavior, and empty states.",
        "Experience configuration",
        "both",
        "ready",
        "Open dashboard packs",
        _link("Super dashboard packs", "super:dashboard_packs_catalog"),
        _link("Dashboard registry", "siteconfig:dashboard_configuration_hub"),
    ),
    ConfigurationModule(
        "policy-bundles",
        "Policy Bundles",
        "Manage rules, approval flows, audit requirements, exceptions, regional compliance, tenant scope, and rollback posture.",
        "Policy governance",
        "both",
        "ready",
        "Open policy bundles",
        _link("Super policies catalog", "super:policies_catalog"),
    ),
    ConfigurationModule(
        "metadata",
        "Metadata Catalog",
        "Review versioned, audited, tenant-safe, region-aware metadata mapped to import, export, lineage, and pack provenance.",
        "Metadata platform",
        "platform_only",
        "ready",
        "Open metadata catalog",
        _link("Metadata operator hub", "siteconfig:metadata_operator_hub"),
    ),
    ConfigurationModule(
        "registries",
        "Registry Center",
        "Expose owners, scopes, generated state, drift posture, route links, proof links, and primary actions for platform registries.",
        "Platform runtime",
        "platform_only",
        "ready",
        "Open registry center",
        _link("Super registry overview", "super:registries_overview"),
        _link("Generated closure map", path="/docs/generated/system_closure_map.json"),
    ),
    ConfigurationModule(
        "runtime",
        "Runtime + Governance",
        "Explain enabled, disabled, blocked, external_required, tenant_scoped, plan_limited, security_blocked, and billing_blocked decisions.",
        "Runtime governance",
        "platform_only",
        "ready",
        "Open runtime truth",
        _link("Runtime truth hub", "super:runtime_truth_hub"),
    ),
    ConfigurationModule(
        "migrations",
        "Migration Center",
        "Coordinate preview, mapping, validation, duplicate detection, quarantine, apply, rollback, acknowledgement, and audit.",
        "Implementation operations",
        "both",
        "ready",
        "Open migration cloud",
        _link("Migration cloud", "super:migration_cloud"),
    ),
    ConfigurationModule(
        "integrations",
        "Integration + API Center",
        "Govern sandbox, scopes, logs, rate limits, replay, owners, test payloads, webhook status, and developer contracts.",
        "Developer platform",
        "both",
        "ready",
        "Open API center",
        _link("API Center", "apicenter:dashboard"),
        _link("Developer ecosystem tests", path="/apps/platform_runtime/tests/test_public_api_lints.py"),
    ),
    ConfigurationModule(
        "compliance",
        "Compliance + Audit Configuration",
        "Track sensitive action actors, timestamps, tenants, reasons, evidence paths, and export integrity.",
        "Trust and compliance",
        "both",
        "ready",
        "Open compliance overview",
        _link("Compliance overview", "super:compliance_overview"),
    ),
    ConfigurationModule(
        "security",
        "Security + Trust Configuration",
        "Separate public trust, platform security operations, security configuration, and tenant school security surfaces.",
        "Enterprise security",
        "both",
        "ready",
        "Open security command center",
        _link("Security command center", "super:security_command_center"),
        _link("Security surface tests", path="/apps/schools/tests/test_super_security_hub.py"),
    ),
    ConfigurationModule(
        "billing",
        "Billing / Subscription / Usage Rules",
        "Distinguish subscription, usage, marketplace app fees, settlement, manual fallback, metadata-ready, and live-verified states.",
        "Billing operations",
        "external_required",
        "external_required",
        "Open billing oversight",
        _link("Platform billing", "super:billing_dashboard"),
        _link("External dependency register", path="/docs/generated/external_dependencies_register.json"),
        "No PSP or settlement surface is labeled live verified without external proof.",
    ),
    ConfigurationModule(
        "experience",
        "UX/UI Experience Configuration",
        "Configure theme, dashboard packs, navigation packs, density, role landing pages, branding, language, accessibility, offline indicators, and primary actions.",
        "Studio OS",
        "both",
        "ready",
        "Open Studio experience",
        _link("Studio experience", "studio_os:experience"),
        _link("Premium UX audit", path="/docs/generated/live_ux_premium_audit.md"),
    ),
)


BLUEPRINTS: tuple[dict[str, object], ...] = (
    {
        "name": "Private Primary School",
        "status": "preview_only",
        "modules": ["Admissions", "Attendance", "Fees", "Reports", "Parent portal"],
        "roles": ["Admin", "Teacher", "Parent", "Student"],
        "dashboard_packs": ["Primary leadership", "Teacher classroom"],
        "workflow_packs": ["Admission intake", "Fee reminder", "Term report publish"],
        "policy_bundles": ["Basic approvals", "Guardian visibility"],
        "report_templates": ["Term report", "Admission letter"],
        "metadata_templates": ["Class levels", "Guardian profile"],
        "billing_defaults": "Subscription plus manual payment fallback",
        "offline_defaults": "Attendance and report draft sync",
    },
    {
        "name": "Private Secondary School",
        "status": "preview_only",
        "modules": ["Academics", "Evaluations", "Discipline", "Fees", "Analytics"],
        "roles": ["Principal", "Dean", "HOD", "Teacher", "Parent", "Student"],
        "dashboard_packs": ["Leadership pulse", "Department performance"],
        "workflow_packs": ["Grade moderation", "Discipline escalation"],
        "policy_bundles": ["Exam approvals", "Student data guardrails"],
        "report_templates": ["Transcript", "Terminal report"],
        "metadata_templates": ["Departments", "Subjects", "Streams"],
        "billing_defaults": "Plan-gated finance and analytics",
        "offline_defaults": "Marks and attendance queues",
    },
    {
        "name": "Cameroon GCE School",
        "status": "preview_only",
        "modules": ["GCE setup", "Subjects", "Reports", "Fees", "Compliance"],
        "roles": ["Principal", "Censor", "Teacher", "Bursar"],
        "dashboard_packs": ["GCE readiness", "Exam operations"],
        "workflow_packs": ["Exam registration", "Report validation"],
        "policy_bundles": ["Regional grading", "Exam audit"],
        "report_templates": ["GCE-style report", "Class list"],
        "metadata_templates": ["Forms", "Series", "Subject groups"],
        "billing_defaults": "Regional currency metadata; PSP external_required if live collection is needed",
        "offline_defaults": "Low-connectivity assessment entry",
    },
    {
        "name": "Bilingual School",
        "status": "preview_only",
        "modules": ["Language packs", "Academics", "Reports", "Parent portal"],
        "roles": ["Admin", "Language coordinator", "Teacher", "Parent"],
        "dashboard_packs": ["Bilingual operations", "Family communications"],
        "workflow_packs": ["Language-specific announcements", "Report translation checks"],
        "policy_bundles": ["Language visibility", "Translation review"],
        "report_templates": ["Bilingual report", "Parent letter"],
        "metadata_templates": ["Language preference", "Program track"],
        "billing_defaults": "Standard plan defaults",
        "offline_defaults": "Localized portal cache",
    },
    {
        "name": "Boarding School",
        "status": "preview_only",
        "modules": ["Hostel", "Attendance", "Discipline", "Fees", "Communication"],
        "roles": ["Boarding manager", "Admin", "Teacher", "Parent"],
        "dashboard_packs": ["Boarding operations", "Student welfare"],
        "workflow_packs": ["Leave request", "Incident escalation"],
        "policy_bundles": ["Guardian approval", "Incident audit"],
        "report_templates": ["Boarding statement", "Incident summary"],
        "metadata_templates": ["Dormitory", "House", "Guardian contacts"],
        "billing_defaults": "Boarding fee categories",
        "offline_defaults": "Attendance and welfare notes",
    },
    {
        "name": "International School",
        "status": "preview_only",
        "modules": ["Curriculum profiles", "Reports", "Compliance", "Payments"],
        "roles": ["Leadership", "Registrar", "Teacher", "Parent"],
        "dashboard_packs": ["International leadership", "Admissions pipeline"],
        "workflow_packs": ["Document review", "Curriculum transition"],
        "policy_bundles": ["Residency and retention", "Data export review"],
        "report_templates": ["International transcript", "Progress report"],
        "metadata_templates": ["Curriculum", "Nationality metadata", "Language"],
        "billing_defaults": "Multi-currency metadata; live PSP external_required by region",
        "offline_defaults": "Portal and document cache",
    },
    {
        "name": "Multi-campus Network",
        "status": "preview_only",
        "modules": ["Group analytics", "Tenant lifecycle", "Billing", "Support"],
        "roles": ["Group admin", "Campus admin", "Finance lead"],
        "dashboard_packs": ["Network command", "Campus comparison"],
        "workflow_packs": ["Campus rollout", "Governed change approval"],
        "policy_bundles": ["Cross-campus governance", "Role delegation"],
        "report_templates": ["Network summary", "Campus scorecard"],
        "metadata_templates": ["Campus groups", "Shared policies"],
        "billing_defaults": "Network subscription and usage posture",
        "offline_defaults": "Campus-local queues",
    },
    {
        "name": "Low-connectivity School",
        "status": "preview_only",
        "modules": ["Offline sync", "Attendance", "Marks", "Reports", "Payments fallback"],
        "roles": ["Admin", "Teacher", "Finance staff"],
        "dashboard_packs": ["Offline readiness", "Sync queue"],
        "workflow_packs": ["Conflict review", "Manual payment reconciliation"],
        "policy_bundles": ["Sync conflict rules", "Manual audit"],
        "report_templates": ["Offline-ready report", "Payment receipt"],
        "metadata_templates": ["Connectivity profile", "Sync owner"],
        "billing_defaults": "Manual fallback; PSP live state external_required",
        "offline_defaults": "High offline coverage and sync conflict center",
    },
)


PACK_LIBRARY: dict[str, tuple[dict[str, object], ...]] = {
    "packages": (
        {
            "name": "Core School OS",
            "target": "tenant school",
            "included_items": ["People", "Academics", "Attendance", "Reports"],
            "owner": "Package operations",
            "setup_effort": "medium",
            "status": "ready",
            "preview_route": "super:package_rollout",
            "install_action": "governed_rollout_only",
        },
        {
            "name": "Growth and Admissions",
            "target": "private schools",
            "included_items": ["Admissions", "Forms", "Lead workflow", "Parent onboarding"],
            "owner": "Implementation factory",
            "setup_effort": "medium",
            "status": "ready",
            "preview_route": "super:package_rollout",
            "install_action": "preview_first",
        },
        {
            "name": "Finance and Payments Readiness",
            "target": "finance teams",
            "included_items": ["Fees", "Invoices", "Manual fallback", "Gateway readiness"],
            "owner": "Billing operations",
            "setup_effort": "high",
            "status": "external_required",
            "preview_route": "super:billing_dashboard",
            "install_action": "metadata_ready_only",
        },
    ),
    "workflow-packs": (
        {
            "name": "Admission Intake",
            "target": "registrar",
            "included_items": ["Form submitted", "Document review", "Decision notification"],
            "owner": "Automation studio",
            "setup_effort": "medium",
            "status": "ready",
            "trigger": "application_submitted",
            "condition": "documents_required",
            "action": "create_review_task",
            "sla": "48h review target",
            "simulation_route": "super:workflow_simulator",
        },
        {
            "name": "Fee Reminder",
            "target": "finance",
            "included_items": ["Invoice due", "Guardian message", "Escalation"],
            "owner": "Automation studio",
            "setup_effort": "low",
            "status": "ready",
            "trigger": "invoice_due",
            "condition": "balance_open",
            "action": "send_reminder",
            "sla": "configurable reminder ladder",
            "simulation_route": "super:workflow_simulator",
        },
        {
            "name": "Offline Conflict Review",
            "target": "IT admin",
            "included_items": ["Conflict detected", "Owner assignment", "Resolution audit"],
            "owner": "Offline-first runtime",
            "setup_effort": "medium",
            "status": "ready",
            "trigger": "sync_conflict_detected",
            "condition": "field_collision",
            "action": "open_resolution_queue",
            "sla": "same-day review",
            "simulation_route": "super:workflow_simulator",
        },
    ),
    "dashboard-packs": (
        {
            "name": "Leadership Pulse",
            "target": "school leadership",
            "included_items": ["Attendance", "Finance", "Academic risk", "Support"],
            "owner": "Experience configuration",
            "setup_effort": "low",
            "status": "ready",
            "widgets": ["risk cards", "trend table", "primary action queue"],
            "metrics": ["attendance rate", "collection posture", "open blockers"],
            "permissions": ["ADMIN", "LEADERSHIP", "PRINCIPAL"],
            "mobile_status": "responsive",
        },
        {
            "name": "Teacher Classroom",
            "target": "teachers",
            "included_items": ["Class list", "Attendance", "Marks", "Messages"],
            "owner": "Experience configuration",
            "setup_effort": "low",
            "status": "ready",
            "widgets": ["today classes", "pending marks", "student notes"],
            "metrics": ["completion", "open actions"],
            "permissions": ["TEACHER"],
            "mobile_status": "responsive",
        },
    ),
    "policy-bundles": (
        {
            "name": "Student Data Governance",
            "target": "tenant school",
            "included_items": ["Visibility", "Audit", "Export review"],
            "owner": "Compliance",
            "setup_effort": "medium",
            "status": "ready",
            "rules": ["role-scoped access", "export audit"],
            "approval_flows": ["sensitive export approval"],
            "audit_requirements": ["actor", "timestamp", "tenant", "reason"],
            "exceptions": ["break-glass audited only"],
            "tenant_scope": "tenant_scoped",
        },
        {
            "name": "Payments Readiness Guard",
            "target": "finance operations",
            "included_items": ["Gateway state", "Manual fallback", "Settlement evidence"],
            "owner": "Billing operations",
            "setup_effort": "high",
            "status": "external_required",
            "rules": ["no live PSP claim without proof", "manual fallback visible"],
            "approval_flows": ["gateway verification"],
            "audit_requirements": ["provider", "environment", "evidence path"],
            "exceptions": ["metadata-ready only"],
            "tenant_scope": "both",
        },
    ),
}


REGISTRIES: tuple[dict[str, str], ...] = (
    {"name": "dashboard_registry", "owner": "Experience configuration", "scope": "both", "status": "ready", "route": "siteconfig:dashboard_configuration_hub", "proof": "/apps/siteconfig/dashboard_registry.py"},
    {"name": "workflow_registry", "owner": "Automation studio", "scope": "both", "status": "ready", "route": "super:workflow_packs_catalog", "proof": "/apps/siteconfig/workflow_registry.py"},
    {"name": "integration_registry", "owner": "Developer platform", "scope": "both", "status": "ready", "route": "super:app_catalog", "proof": "/apps/siteconfig/integration_registry.py"},
    {"name": "billing_sku_registry", "owner": "Billing operations", "scope": "platform_only", "status": "ready", "route": "super:billing_dashboard", "proof": "/apps/siteconfig/billing_sku_registry.py"},
    {"name": "brand_registry", "owner": "Experience configuration", "scope": "both", "status": "ready", "route": "studio_os:experience", "proof": "/apps/siteconfig/brand_registry.py"},
    {"name": "extension_registry", "owner": "Marketplace governance", "scope": "platform_only", "status": "ready", "route": "super:marketplace_governance", "proof": "/apps/marketplace/extension_registry.py"},
    {"name": "pack_registry", "owner": "Package operations", "scope": "platform_only", "status": "ready", "route": "super:package_rollout", "proof": "/apps/marketplace/pack_registry.py"},
    {"name": "usage_registry", "owner": "Billing operations", "scope": "platform_only", "status": "ready", "route": "super:usage", "proof": "/apps/marketplace/usage_registry.py"},
    {"name": "owned_models_registry", "owner": "Platform runtime", "scope": "platform_only", "status": "ready", "route": "super:registries_overview", "proof": "/docs/generated/route_surface_audit.json"},
    {"name": "external_dependency_register", "owner": "External readiness", "scope": "external_required", "status": "external_required", "route": "super:trust_center", "proof": "/docs/generated/external_dependencies_register.json"},
)


TENANT_CONFIGURATION_SECTIONS: tuple[dict[str, str], ...] = (
    {"name": "School Profile", "status": "ready", "missing": "none", "route": "/siteconfig/console/", "primary_action": "Open profile configuration"},
    {"name": "Academic Year / Term", "status": "ready", "missing": "none", "route": "/siteconfig/academic-years/", "primary_action": "Review academic year setup"},
    {"name": "Classes / Subjects", "status": "ready", "missing": "none", "route": "/academics/", "primary_action": "Open academic structure"},
    {"name": "Grading Rules", "status": "ready", "missing": "none", "route": "/siteconfig/grading-settings/", "primary_action": "Open grading rules"},
    {"name": "Report Templates", "status": "ready", "missing": "none", "route": "/siteconfig/reports/builder/", "primary_action": "Open report builder"},
    {"name": "Fees", "status": "ready", "missing": "PSP live collection can remain external_required", "route": "/finance/", "primary_action": "Open money center"},
    {"name": "Roles / Permissions", "status": "ready", "missing": "none", "route": "/admin/", "primary_action": "Open technical role records"},
    {"name": "Parent Portal", "status": "ready", "missing": "none", "route": "/portal/", "primary_action": "Open parent portal preview"},
    {"name": "Teacher Portal", "status": "ready", "missing": "none", "route": "/portal/teacher/", "primary_action": "Open teacher workspace"},
    {"name": "Apps", "status": "ready", "missing": "marketplace monetization external_required", "route": "/settings/app-catalog/", "primary_action": "Open school app catalog"},
    {"name": "Workflows", "status": "ready", "missing": "none", "route": "/studio/automation/", "primary_action": "Open automation studio"},
    {"name": "Offline Settings", "status": "ready", "missing": "none", "route": "/portal/offline-sync/", "primary_action": "Open offline sync"},
    {"name": "Branding / Theme", "status": "ready", "missing": "none", "route": "/siteconfig/school-theme/", "primary_action": "Open school theme"},
    {"name": "Security / Audit", "status": "ready", "missing": "none", "route": "/compliance/", "primary_action": "Open school audit"},
)


def enriched_modules() -> list[dict[str, str]]:
    modules: list[dict[str, str]] = []
    for module in CONFIGURATION_MODULES:
        modules.append(
            {
                "key": module.key,
                "title": module.title,
                "purpose": module.purpose,
                "owner": module.owner,
                "scope": module.scope,
                "status": module.status,
                "primary_action": module.primary_action,
                "existing_route_label": module.existing_route.label,
                "existing_route_url": resolve_surface_link(module.existing_route),
                "proof_label": module.proof.label,
                "proof_url": resolve_surface_link(module.proof),
                "detail": module.detail,
                "configuration_url": f"/configuration/{module.key}/",
            }
        )
    return modules


def module_by_key(key: str) -> dict[str, str] | None:
    return next((m for m in enriched_modules() if m["key"] == key), None)


def resolved_pack_rows(pack_key: str) -> list[dict[str, object]]:
    rows = []
    for pack in PACK_LIBRARY.get(pack_key, ()):
        row = dict(pack)
        route_name = str(row.get("preview_route") or "")
        row["preview_url"] = resolve_surface_link(_link("Preview", route_name=route_name))
        sim = str(row.get("simulation_route") or "")
        if sim:
            row["simulation_url"] = resolve_surface_link(_link("Simulation", route_name=sim))
        else:
            row["simulation_url"] = ""
        rows.append(row)
    return rows


def resolved_registry_rows() -> list[dict[str, str]]:
    rows = []
    for registry in REGISTRIES:
        row = dict(registry)
        row["route_url"] = resolve_surface_link(_link("Route", route_name=row.get("route", "")))
        row["drift_status"] = "tracked"
        row["last_generated"] = "see proof"
        rows.append(row)
    return rows


def all_surface_map_rows() -> Iterable[dict[str, str]]:
    for module in enriched_modules():
        yield {
            "current_route": module["existing_route_url"],
            "current_template_view": module["existing_route_label"],
            "current_user": module["owner"],
            "belongs_to": "/configuration",
            "current_status": module["status"],
            "risk": "external proof required" if module["status"] == "external_required" else "facade drift",
            "recommended_action": module["primary_action"],
            "tests_needed": "configuration center access, route links, tenant boundary",
        }
    for section in TENANT_CONFIGURATION_SECTIONS:
        yield {
            "current_route": section["route"],
            "current_template_view": section["name"],
            "current_user": "tenant school admin",
            "belongs_to": "/school",
            "current_status": section["status"],
            "risk": section["missing"],
            "recommended_action": section["primary_action"],
            "tests_needed": "tenant school configuration access and platform registry exclusion",
        }
