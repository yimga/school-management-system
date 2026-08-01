"""Administration and configuration surface catalog.

This module is intentionally data-first: the /configuration/ product surface is
a facade over existing RunMyCampus systems, not a new source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from django.urls import NoReverseMatch, get_urlconf, reverse
from django.utils.translation import gettext_lazy as _

from apps.platform_runtime.blueprint_contract import list_blueprints


EXTERNAL_DEPENDENCIES_REGISTER_PATH = "/docs/generated/external_dependencies_register.json"


MODULE_STATUS_READINESS: dict[str, dict[str, object]] = {
    "ready": {
        "score": 100,
        "code_score": 100,
        "external_score": 100,
        "token": "ready",
        "tone": "success",
        "label": _("Ready"),
        "readiness_label": _("Local proof complete"),
    },
    "partial": {
        "score": 100,
        "code_score": 100,
        "external_score": 60,
        "token": "partial",
        "tone": "warning",
        "label": _("Code ready · external pending"),
        "readiness_label": _("Code shipped; external proof tracked in SOT"),
    },
    "external_required": {
        "score": 100,
        "code_score": 100,
        "external_score": 40,
        "token": "external-required",
        "tone": "info",
        "label": _("Code ready · external required"),
        "readiness_label": _("Code shipped; external dependency tracked in SOT"),
    },
    "beta": {
        "score": 80,
        "code_score": 80,
        "external_score": 100,
        "token": "beta",
        "tone": "info",
        "label": _("Beta"),
        "readiness_label": _("Stabilizing"),
    },
    "danger": {
        "score": 20,
        "code_score": 20,
        "external_score": 100,
        "token": "danger",
        "tone": "danger",
        "label": _("Danger"),
        "readiness_label": _("Needs intervention"),
    },
}

DEFAULT_MODULE_READINESS: dict[str, object] = {
    "score": 50,
    "code_score": 50,
    "external_score": 100,
    "token": "needs-review",
    "tone": "secondary",
    "label": _("Needs review"),
    "readiness_label": _("Awaiting proof"),
}


MODULE_TO_SOT_REGISTER_IDS: dict[str, tuple[str, ...]] = {
    "app-catalog": (
        "stripe_global_cards",
        "paystack_wa",
        "flutterwave_multi_country",
        "bank_sepa_card_partner",
    ),
    "billing": (
        "stripe_global_cards",
        "paystack_wa",
        "flutterwave_multi_country",
        "mtn_momo",
        "orange_money",
        "bank_sepa_card_partner",
        "manual_fallback_operations",
    ),
}


def _readiness_for(status: str) -> dict[str, object]:
    return MODULE_STATUS_READINESS.get(status, DEFAULT_MODULE_READINESS)


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
        "Open theme & experience hub",
        _link("Theme & experience hub", "siteconfig:theme_experience_hub"),
        _link("Premium UX audit", path="/docs/generated/live_ux_premium_audit.md"),
        detail=(
            "Dual-plane configurability: tenants use the school hub on the tenant host; "
            "operators use this hub on manager.runmycampus.com plus RuntimeDefaults public brand."
        ),
    ),
)


BLUEPRINTS: tuple[dict[str, object], ...] = tuple(list_blueprints())


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
    {
        "name": "dashboard_registry",
        "owner": "Experience configuration",
        "scope": "both",
        "status": "ready",
        "route": "siteconfig:dashboard_configuration_hub",
        "proof": "/apps/siteconfig/dashboard_registry.py",
        "test": "apps/platform_runtime/tests/test_registry_health_dashboard.py",
    },
    {
        "name": "workflow_registry",
        "owner": "Automation studio",
        "scope": "both",
        "status": "ready",
        "route": "super:workflow_packs_catalog",
        "proof": "/apps/siteconfig/workflow_registry.py",
        "test": "apps/platform_runtime/tests/test_registry_drift_detection.py",
    },
    {
        "name": "integration_registry",
        "owner": "Developer platform",
        "scope": "both",
        "status": "ready",
        "route": "super:app_catalog",
        "proof": "/apps/siteconfig/integration_registry.py",
        "test": "apps/siteconfig/tests/test_integration_registry.py",
    },
    {
        "name": "billing_sku_registry",
        "owner": "Billing operations",
        "scope": "platform_only",
        "status": "ready",
        "route": "super:billing_dashboard",
        "proof": "/apps/siteconfig/billing_sku_registry.py",
        "test": "apps/siteconfig/tests/test_billing_sku_registry.py",
    },
    {
        "name": "brand_registry",
        "owner": "Experience configuration",
        "scope": "both",
        "status": "ready",
        "route": "studio_os:experience",
        "proof": "/apps/siteconfig/brand_registry.py",
        "test": "apps/siteconfig/tests/test_global_brand_registry.py",
    },
    {
        "name": "extension_registry",
        "owner": "Marketplace governance",
        "scope": "platform_only",
        "status": "ready",
        "route": "super:marketplace_governance",
        "proof": "/apps/marketplace/extension_registry.py",
        "test": "apps/marketplace/tests/test_workflow_hook_registry.py",
    },
    {
        "name": "pack_registry",
        "owner": "Package operations",
        "scope": "platform_only",
        "status": "ready",
        "route": "super:package_rollout",
        "proof": "/apps/marketplace/pack_registry.py",
        "test": "apps/billing/tests/test_package_rollout_lifecycle.py",
    },
    {
        "name": "usage_registry",
        "owner": "Billing operations",
        "scope": "platform_only",
        "status": "ready",
        "route": "super:usage",
        "proof": "/apps/marketplace/usage_registry.py",
        "test": "apps/metadata/tests/test_usage_registry_helpers.py",
    },
    {
        "name": "owned_models_registry",
        "owner": "Platform runtime",
        "scope": "platform_only",
        "status": "ready",
        "route": "super:registries_overview",
        "proof": "/docs/generated/route_surface_audit.json",
        "test": "apps/dashboard/tests/test_phase8_registry_full_coverage.py",
    },
    {
        "name": "external_dependency_register",
        "owner": "External readiness",
        "scope": "external_required",
        "status": "external_required",
        "route": "super:trust_center",
        "proof": "/docs/generated/external_dependencies_register.json",
        "test": "apps/platform_runtime/tests/test_registry_center.py",
    },
)


# Each section carries a ``permission`` code: the granular RBAC permission that gates the
# surface the section links to. The config-hub template renders a section only when the
# viewer holds that code (or the tenant-admin tier), so a delegated non-admin — a bursar
# granted finance.view, a DPO granted compliance.view — sees exactly the config surfaces they
# can actually open, instead of a wall of cards that 403 on click.
# Static catalog routes only — status/missing are resolved live by
# ``enrich_tenant_configuration_sections`` (MAX Wave 1: no wallpaper "ready").
TENANT_CONFIGURATION_SECTIONS: tuple[dict[str, str], ...] = (
    {"name": "School Profile", "status": "", "missing": "", "route_name": "siteconfig:console_domains_hub", "primary_action": "Open profile configuration", "permission": "settings.manage", "probe": "school_created"},
    {"name": "Academic Year / Term", "status": "", "missing": "", "route_name": "siteconfig:academic_years_setup_evidence", "primary_action": "Review academic year setup", "permission": "settings.manage", "probe": "academic_year"},
    {"name": "Classes / Subjects", "status": "", "missing": "", "route_name": "academics:hub", "primary_action": "Open academic structure", "permission": "settings.manage", "probe": "classes"},
    {"name": "Grading Rules", "status": "", "missing": "", "route_name": "siteconfig:grading_settings", "primary_action": "Open grading rules", "permission": "grades.manage", "probe": "grading"},
    {"name": "Report Templates", "status": "", "missing": "", "route_name": "siteconfig:reportcard_builder", "primary_action": "Open report builder", "permission": "reports.manage", "probe": "reports"},
    {"name": "Fees", "status": "", "missing": "", "route_name": "finance:dashboard", "primary_action": "Open money center", "permission": "finance.view", "probe": "fees"},
    {"name": "Roles / Permissions", "status": "", "missing": "", "route_name": "tenant_admin:index", "primary_action": "Open technical role records", "permission": "settings.manage", "probe": "roles"},
    {"name": "Parent Portal", "status": "", "missing": "", "route_name": "portal:parent_dashboard", "primary_action": "Open parent portal preview", "permission": "portal.manage", "probe": "portal"},
    {"name": "Teacher Portal", "status": "", "missing": "", "route_name": "portal:teacher_dashboard_alias", "primary_action": "Open teacher workspace", "permission": "portal.manage", "probe": "portal"},
    {"name": "Apps", "status": "", "missing": "", "route_name": "tenant_app_catalog", "primary_action": "Open school app catalog", "permission": "settings.manage", "probe": "apps"},
    {"name": "Workflows", "status": "", "missing": "", "route_name": "studio_os:automation", "primary_action": "Open automation studio", "permission": "settings.manage", "probe": "workflows"},
    {"name": "Offline Settings", "status": "", "missing": "", "route_name": "portal:offline_sync_queue", "primary_action": "Open offline sync", "permission": "settings.manage", "probe": "offline"},
    {
        "name": "Branding / Theme",
        "status": "",
        "missing": "",
        "route_name": "siteconfig:theme_experience_hub",
        "primary_action": "Open theme & experience hub",
        "permission": "settings.manage",
        "probe": "branding",
    },
    {"name": "Security / Audit", "status": "", "missing": "", "route_name": "compliance:dashboard", "primary_action": "Open school audit", "permission": "compliance.view", "probe": "audit"},
)


def _resolve_tenant_configuration_route(section, *, request=None, urlconf=None) -> tuple[str, str]:
    """Resolve a configuration action through the tenant URL registry.

    Missing ownership fails closed: callers receive an empty href plus a useful
    diagnostic instead of shipping another tenant-scoped 404.
    """
    route_name = str(section.get("route_name") or "")
    active_urlconf = urlconf or getattr(request, "urlconf", None) or get_urlconf() or "config.tenant_urls"
    try:
        return reverse(route_name, urlconf=active_urlconf), ""
    except (NoReverseMatch, TypeError, ValueError):
        return "", f"Route unavailable: {route_name}"


def enrich_tenant_configuration_sections(school, *, request=None, user=None) -> list[dict[str, object]]:
    """Resolve live status tags for School Configuration Center cards.

    Maps setup_health_score checks + lightweight presence probes onto the locked
    vocabulary (healthy / attention / needs_setup). Never returns wallpaper ``ready``.
    """
    from apps.platform_runtime.page_status_tags import (
        STATUS_ATTENTION,
        STATUS_HEALTHY,
        STATUS_LABELS,
        STATUS_NEEDS_SETUP,
        STATUS_VARIANTS,
    )
    from apps.schools.setup_health import setup_health_score

    health = setup_health_score(school, user=user)
    check_map = {name: bool(passed) for name, passed, _label in health.get("checks", [])}

    def _probe(name: str) -> tuple[str, str]:
        if name == "school_created":
            ok = check_map.get("school_created", bool(school))
            return (STATUS_HEALTHY if ok else STATUS_NEEDS_SETUP, "" if ok else "School profile incomplete")
        if name == "branding":
            ok = check_map.get("branding", False)
            return (STATUS_HEALTHY if ok else STATUS_NEEDS_SETUP, "" if ok else "Branding not set")
        if name == "plan" or name == "fees":
            # Fees: plan assigned = healthy; else attention (PSP may still be external).
            ok = check_map.get("plan", False)
            if ok:
                return (STATUS_ATTENTION, "PSP live collection may remain external")
            return (STATUS_NEEDS_SETUP, "Plan not assigned")
        if name == "academic_year":
            try:
                from apps.academics.models import AcademicYear  # type: ignore

                # tenant-isolation-allow: request-school-scoped-config-enrichment
                qs = AcademicYear.objects.filter(school=school)
                if not qs.exists():
                    return (STATUS_NEEDS_SETUP, "No academic year")
                if qs.filter(is_active=True).exists():
                    return (STATUS_HEALTHY, "")
                return (STATUS_ATTENTION, "No active term / year")
            except Exception:
                return (STATUS_ATTENTION, "Unable to verify academic year")
        if name == "classes":
            try:
                from apps.academics.models import Classroom  # type: ignore

                # tenant-isolation-allow: request-school-scoped-config-enrichment
                exists = Classroom.objects.filter(school=school).exists()
                return (STATUS_HEALTHY if exists else STATUS_NEEDS_SETUP, "" if exists else "No classes yet")
            except Exception:
                return (STATUS_ATTENTION, "Unable to verify classes")
        if name in {"grading", "reports", "roles", "portal", "apps", "workflows", "offline", "audit"}:
            # Reachable surfaces with no hard blocker — healthy once school exists.
            ok = check_map.get("school_created", bool(school))
            return (STATUS_HEALTHY if ok else STATUS_NEEDS_SETUP, "" if ok else "Complete school profile first")
        return (STATUS_ATTENTION, "Review recommended")

    rows: list[dict[str, object]] = []
    for section in TENANT_CONFIGURATION_SECTIONS:
        probe = section.get("probe", "school_created")
        key, missing = _probe(probe)
        route, route_error = _resolve_tenant_configuration_route(section, request=request)
        if route_error:
            key = STATUS_NEEDS_SETUP
            missing = route_error
        rows.append(
            {
                **section,
                "route": route,
                "route_error": route_error,
                "action_disabled": bool(route_error),
                "status": STATUS_LABELS[key],
                "status_key": key,
                "status_tone": STATUS_VARIANTS[key],
                "missing": missing or "—",
            }
        )
    return rows



def enriched_modules() -> list[dict[str, object]]:
    modules: list[dict[str, object]] = []
    for module in CONFIGURATION_MODULES:
        readiness = _readiness_for(module.status)
        sot_ids = MODULE_TO_SOT_REGISTER_IDS.get(module.key, ())
        modules.append(
            {
                "key": module.key,
                "title": module.title,
                "purpose": module.purpose,
                "owner": module.owner,
                "scope": module.scope,
                "status": module.status,
                "status_label": readiness["label"],
                "status_tone": readiness["tone"],
                "readiness_score": readiness["code_score"],
                "code_readiness_score": readiness["code_score"],
                "external_readiness_score": readiness["external_score"],
                "readiness_token": readiness["token"],
                "readiness_label": readiness["readiness_label"],
                "sot_register_ids": sot_ids,
                "sot_register_url": EXTERNAL_DEPENDENCIES_REGISTER_PATH,
                "has_external_dependency": bool(sot_ids),
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


def module_by_key(key: str) -> dict[str, object] | None:
    return next((m for m in enriched_modules() if m["key"] == key), None)


def compute_configuration_summary() -> dict[str, object]:
    modules = enriched_modules()
    total = len(modules)
    if total == 0:
        return {
            "readiness_pct": 0,
            "readiness_display": "0%",
            "readiness_label": _("No modules registered"),
            "code_readiness_pct": 0,
            "external_readiness_pct": 0,
            "risk_level": _("Unknown"),
            "risk_label": _("Catalog empty"),
            "next_step": _("Review"),
            "next_step_label": _("Change queue"),
            "blockers_count": 0,
            "blockers_display": "0",
            "blockers_label": _("No external dependencies"),
            "external_blocker_keys": [],
            "external_sot_ids": [],
            "external_sot_url": EXTERNAL_DEPENDENCIES_REGISTER_PATH,
        }

    code_score_sum = sum(int(m["code_readiness_score"]) for m in modules)
    external_score_sum = sum(int(m["external_readiness_score"]) for m in modules)
    code_readiness_pct = round(code_score_sum / total)
    external_readiness_pct = round(external_score_sum / total)

    external_modules = [m for m in modules if m["has_external_dependency"]]
    blockers_count = len(external_modules)
    aggregate_sot_ids: list[str] = []
    for m in external_modules:
        for sot_id in m["sot_register_ids"]:
            if sot_id not in aggregate_sot_ids:
                aggregate_sot_ids.append(sot_id)

    if code_readiness_pct >= 100 and blockers_count == 0:
        risk_level = _("Low")
        risk_label = _("All proof complete")
    elif code_readiness_pct >= 100:
        risk_level = _("Low")
        risk_label = _("Code complete; external proof tracked in SOT")
    elif code_readiness_pct >= 90:
        risk_level = _("Low")
        risk_label = _("Repository proof complete")
    elif code_readiness_pct >= 70:
        risk_level = _("Medium")
        risk_label = _("Live parity pending")
    else:
        risk_level = _("High")
        risk_label = _("Multiple modules unproven")

    if blockers_count == 0:
        blockers_display = _("None")
        blockers_label = _("No external dependencies")
    else:
        blockers_display = str(blockers_count)
        blockers_label = _("External dependencies tracked in SOT")

    return {
        "readiness_pct": code_readiness_pct,
        "readiness_display": f"{code_readiness_pct}%",
        "readiness_label": _("Code readiness"),
        "code_readiness_pct": code_readiness_pct,
        "external_readiness_pct": external_readiness_pct,
        "risk_level": risk_level,
        "risk_label": risk_label,
        "next_step": _("Review"),
        "next_step_label": _("Change queue"),
        "blockers_count": blockers_count,
        "blockers_display": blockers_display,
        "blockers_label": blockers_label,
        "external_blocker_keys": [m["key"] for m in external_modules],
        "external_sot_ids": aggregate_sot_ids,
        "external_sot_url": EXTERNAL_DEPENDENCIES_REGISTER_PATH,
    }


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


def validate_sot_register_linkage() -> dict[str, object]:
    """Return whether every module's referenced SOT IDs exist in the register.

    Returns a dict with `missing_ids` (module_key -> [unknown ids]) and `register_ids`
    (the set of IDs actually present in the generated register).
    """
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    register_path = repo_root / "docs" / "generated" / "external_dependencies_register.json"
    register_ids: set[str] = set()
    if register_path.exists():
        try:
            data = json.loads(register_path.read_text(encoding="utf-8"))
            for entry in data.get("entries_flat", []) or []:
                eid = entry.get("id")
                if eid:
                    register_ids.add(str(eid))
        except (OSError, ValueError):
            pass
    missing: dict[str, list[str]] = {}
    for module_key, sot_ids in MODULE_TO_SOT_REGISTER_IDS.items():
        unknown = [sid for sid in sot_ids if sid not in register_ids]
        if unknown:
            missing[module_key] = unknown
    return {
        "register_path_exists": register_path.exists(),
        "register_ids": sorted(register_ids),
        "missing_ids": missing,
    }


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
        route, route_error = _resolve_tenant_configuration_route(
            section, urlconf="config.tenant_urls"
        )
        yield {
            "current_route": route,
            "current_template_view": section["name"],
            "current_user": "tenant school admin",
            "belongs_to": "/school",
            "current_status": section["status"],
            "risk": route_error or section["missing"],
            "recommended_action": section["primary_action"],
            "tests_needed": "tenant school configuration access and platform registry exclusion",
        }
