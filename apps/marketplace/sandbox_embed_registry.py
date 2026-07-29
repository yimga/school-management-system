"""
Sandbox embed URL registry for marketplace catalog apps (73 slugs).

TOP_15 entries are explicit; remaining slugs infer tenant-safe demo surfaces
from prefix rules. Widget configs store ``url_name``; ``sandbox_embed`` resolves
at request time (same-origin relative paths).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.marketplace.capability_contract import TOP_15_APP_SLUGS

TENANT_URLCONF = "config.tenant_urls"


@dataclass(frozen=True)
class SandboxEmbedSpec:
    widget_id: str
    url_name: str
    title: str = ""
    surface: str = "backend"
    url_kwargs: dict[str, Any] = field(default_factory=dict)


# Canonical demo surfaces for priority catalog apps (tenant urlconf names).
SANDBOX_EMBED_REGISTRY: dict[str, tuple[SandboxEmbedSpec, ...]] = {
    "billing-fees-pack": (
        SandboxEmbedSpec(
            widget_id="billing_fees_preview",
            url_name="finance:generate_fees",
            title="Fee generation",
            surface="finance",
        ),
    ),
    "parent-engagement-pack": (
        SandboxEmbedSpec(
            widget_id="parent_engagement_preview",
            url_name="portal:parent_workflow",
            title="Parent workflow",
            surface="portal",
        ),
    ),
    "transport-bus-tracker": (
        SandboxEmbedSpec(
            widget_id="transport_ops_preview",
            url_name="accounts:ops_transport",
            title="Transport routes",
            surface="schoolops",
        ),
    ),
    "cafeteria-meal-plans": (
        SandboxEmbedSpec(
            widget_id="canteen_ops_preview",
            url_name="accounts:ops_canteen",
            title="Cafeteria & meals",
            surface="schoolops",
        ),
    ),
    "sso-identity": (
        SandboxEmbedSpec(
            widget_id="sso_security_preview",
            url_name="accounts:sso_connections",
            title="Security & SSO",
            surface="settings",
        ),
    ),
    "sis-bridge-oneroster-v1p2": (
        SandboxEmbedSpec(
            widget_id="sis_migration_preview",
            url_name="school_studio_migration",
            title="SIS migration studio",
            surface="studio",
        ),
    ),
    "messaging-sms-gateway": (
        SandboxEmbedSpec(
            widget_id="messaging_sms_preview",
            url_name="portal:preview_communication_test",
            title="Communication preview",
            surface="portal",
        ),
    ),
    "payments-paystack": (
        SandboxEmbedSpec(
            widget_id="payments_paystack_preview",
            url_name="finance:payment_readiness_setup",
            title="Payment readiness",
            surface="finance",
        ),
    ),
    "payments-flutterwave-momo": (
        SandboxEmbedSpec(
            widget_id="payments_flutterwave_preview",
            url_name="finance:global_payment_command_center",
            title="Global payments",
            surface="finance",
        ),
    ),
    "advanced-workflow-builder": (
        SandboxEmbedSpec(
            widget_id="workflow_builder_preview",
            url_name="studio_os:workflow_center",
            title="Workflow center",
            surface="studio",
        ),
    ),
    "compliance-export": (
        SandboxEmbedSpec(
            widget_id="compliance_export_panel",
            url_name="siteconfig:compliance_exports",
            title="Compliance exports",
            surface="compliance",
        ),
    ),
    "student-360-pack": (
        SandboxEmbedSpec(
            widget_id="student_360_summary",
            url_name="accounts:backend_student_list",
            title="Student roster (360 entry)",
            surface="backend",
        ),
    ),
    "onboarding-wizard-pack": (
        SandboxEmbedSpec(
            widget_id="onboarding_wizard_entry",
            url_name="siteconfig:onboarding",
            title="School onboarding",
            surface="onboarding",
        ),
    ),
    "api-webhooks-pack": (
        SandboxEmbedSpec(
            widget_id="api_webhooks_preview",
            url_name="apicenter:webhook_docs",
            title="Webhook documentation",
            surface="apicenter",
        ),
    ),
    "analytics-insights-pack": (
        SandboxEmbedSpec(
            widget_id="insights_kpi_strip",
            url_name="analytics:event_analytics_dashboard",
            title="Event analytics",
            surface="analytics",
        ),
    ),
}

# Additional explicit surfaces beyond TOP_15 (non-overlapping slugs).
CATALOG_EMBED_OVERRIDES: dict[str, SandboxEmbedSpec] = {
    "admissions-lead-tracker": SandboxEmbedSpec(
        widget_id="admissions_pipeline_preview",
        url_name="siteconfig:guided_onboarding",
        title="Admissions pipeline",
        surface="admissions",
    ),
    "attendance-intervention-pack": SandboxEmbedSpec(
        widget_id="attendance_intervention_preview",
        url_name="accounts:backend_dashboard",
        title="Attendance dashboard",
        surface="backend",
    ),
    "grade-publishing-pack": SandboxEmbedSpec(
        widget_id="grade_publish_preview",
        url_name="portal:teacher_workflow",
        title="Grade publishing",
        surface="portal",
    ),
    "compliance-audit-pack": SandboxEmbedSpec(
        widget_id="compliance_audit_preview",
        url_name="siteconfig:compliance_exports",
        title="Compliance audit exports",
        surface="compliance",
    ),
    "reporting-export-pack": SandboxEmbedSpec(
        widget_id="reporting_export_preview",
        url_name="finance:reports",
        title="Finance reports",
        surface="finance",
    ),
    "library-asset-tracker": SandboxEmbedSpec(
        widget_id="library_ops_preview",
        url_name="accounts:ops_library",
        title="Library assets",
        surface="schoolops",
    ),
    "boarding-house-management": SandboxEmbedSpec(
        widget_id="boarding_ops_preview",
        url_name="accounts:ops_inventory",
        title="Boarding inventory",
        surface="schoolops",
    ),
    "transport-route-optimizer": SandboxEmbedSpec(
        widget_id="transport_route_preview",
        url_name="accounts:ops_transport",
        title="Transport routes",
        surface="schoolops",
    ),
    "medical-clinic-records": SandboxEmbedSpec(
        widget_id="clinic_ops_preview",
        url_name="accounts:ops_clinic",
        title="Clinic records",
        surface="schoolops",
    ),
    "migration-connector-pack": SandboxEmbedSpec(
        widget_id="migration_connector_preview",
        url_name="school_studio_migration",
        title="Migration connector",
        surface="studio",
    ),
    "enterprise-governance-console": SandboxEmbedSpec(
        widget_id="governance_console_preview",
        url_name="school_audit",
        title="Governance audit",
        surface="settings",
    ),
    "district-pack": SandboxEmbedSpec(
        widget_id="district_pack_preview",
        url_name="analytics:executive_dashboard",
        title="District executive view",
        surface="analytics",
    ),
    "procurement-vendor-management": SandboxEmbedSpec(
        widget_id="procurement_preview",
        url_name="finance:reports",
        title="Procurement reports",
        surface="finance",
    ),
    "backup-disaster-recovery": SandboxEmbedSpec(
        widget_id="backup_dr_preview",
        url_name="school_audit",
        title="Backup & DR",
        surface="settings",
    ),
    "portal-themes-pack": SandboxEmbedSpec(
        widget_id="portal_themes_preview",
        url_name="school_configuration_center",
        title="Portal themes",
        surface="settings",
    ),
    "premium-communication-pack": SandboxEmbedSpec(
        widget_id="communication_preview",
        url_name="portal:preview_communication_test",
        title="Communication hub",
        surface="portal",
    ),
}

_CATALOG_PREFIX_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("sis-bridge-", "school_studio_migration", "SIS bridge", "studio"),
    ("lms-bridge-", "portal:teacher_workflow", "LMS bridge", "portal"),
    ("payments-", "finance:payment_readiness_setup", "Payments", "finance"),
    ("messaging-", "portal:preview_communication_test", "Messaging", "communication"),
    ("identity-", "school_security", "Identity SSO", "security"),
    ("country-bundle-", "siteconfig:onboarding", "Country bundle", "onboarding"),
    ("specialty-", "accounts:backend_student_list", "Specialty program", "backend"),
    ("iot-", "accounts:backend_dashboard", "IoT adapter", "backend"),
    ("alumni-", "portal:parent_workflow", "Alumni", "portal"),
)

_DEFAULT_CATALOG_EMBED = SandboxEmbedSpec(
    widget_id="catalog_app_preview",
    url_name="accounts:backend_dashboard",
    title="School backend preview",
    surface="backend",
)


def _widget_id_for_slug(slug: str, *, suffix: str = "preview") -> str:
    safe = (slug or "").replace("-", "_")
    return f"{safe}_{suffix}"


def _infer_embed_spec(slug: str) -> SandboxEmbedSpec:
    slug = (slug or "").strip()
    if slug in CATALOG_EMBED_OVERRIDES:
        return CATALOG_EMBED_OVERRIDES[slug]
    lowered = slug.lower()
    for prefix, url_name, title, surface in _CATALOG_PREFIX_RULES:
        if lowered.startswith(prefix):
            label = slug[len(prefix) :].replace("-", " ").title() or slug
            return SandboxEmbedSpec(
                widget_id=_widget_id_for_slug(slug),
                url_name=url_name,
                title=f"{title} — {label}",
                surface=surface,
            )
    return SandboxEmbedSpec(
        widget_id=_widget_id_for_slug(slug),
        url_name=_DEFAULT_CATALOG_EMBED.url_name,
        title=_DEFAULT_CATALOG_EMBED.title,
        surface=_DEFAULT_CATALOG_EMBED.surface,
    )


def registry_specs_for_slug(slug: str) -> tuple[SandboxEmbedSpec, ...]:
    slug = (slug or "").strip()
    if slug in SANDBOX_EMBED_REGISTRY:
        return SANDBOX_EMBED_REGISTRY[slug]
    return (_infer_embed_spec(slug),)


def widgets_dict_for_slug(slug: str) -> dict[str, dict[str, Any]]:
    """Manifest-ready widget map with url_name for sandbox iframe resolution."""
    widgets: dict[str, dict[str, Any]] = {}
    for spec in registry_specs_for_slug(slug):
        widgets[spec.widget_id] = {
            "widget_id": spec.widget_id,
            "title": spec.title or spec.widget_id.replace("_", " ").title(),
            "surface": spec.surface,
            "url_name": spec.url_name,
            "sandbox_demo": True,
        }
        if spec.url_kwargs:
            widgets[spec.widget_id]["url_kwargs"] = dict(spec.url_kwargs)
    return widgets


def merge_sandbox_widgets_into_manifest(
    slug: str, manifest: dict[str, Any] | None
) -> dict[str, Any]:
    """Non-destructive merge of registry widgets into manifest.widgets."""
    base = dict(manifest) if isinstance(manifest, dict) else {}
    registry_widgets = widgets_dict_for_slug(slug)
    if not registry_widgets:
        return base
    existing = base.get("widgets")
    merged = dict(existing) if isinstance(existing, dict) else {}
    for wid, cfg in registry_widgets.items():
        if wid not in merged:
            merged[wid] = cfg
        elif isinstance(merged[wid], dict) and not merged[wid].get("url"):
            merged[wid] = {**cfg, **merged[wid]}
    base["widgets"] = merged
    return base


def _resolve_url_name(
    url_name: str,
    *,
    url_kwargs: dict[str, Any] | None = None,
    request=None,
) -> str | None:
    from django.urls import NoReverseMatch, reverse

    kwargs = dict(url_kwargs or {})
    try:
        if request is not None:
            return reverse(url_name, kwargs=kwargs)
        return reverse(url_name, kwargs=kwargs, urlconf=TENANT_URLCONF)
    except NoReverseMatch:
        return None


def resolve_widget_iframe_src(
    widget_cfg: dict[str, Any] | None,
    *,
    request=None,
) -> str | None:
    if not isinstance(widget_cfg, dict):
        return None
    direct = str(widget_cfg.get("url") or "").strip()
    if direct:
        return direct
    url_name = str(widget_cfg.get("url_name") or "").strip()
    if not url_name:
        return None
    kwargs = widget_cfg.get("url_kwargs")
    if not isinstance(kwargs, dict):
        kwargs = {}
    return _resolve_url_name(url_name, url_kwargs=kwargs, request=request)


def resolve_sandbox_iframe_src(
    *,
    app_slug: str,
    widget_config: dict[str, Any] | None,
    widget_id: str = "",
    request=None,
) -> str | None:
    """Pick iframe src from installation widget_config, manifest widgets, or registry."""
    wconfig = widget_config if isinstance(widget_config, dict) else {}
    wid = (widget_id or "").strip()

    if wid and wid in wconfig:
        src = resolve_widget_iframe_src(wconfig[wid], request=request)
        if src:
            return src

    for cfg in wconfig.values():
        if isinstance(cfg, dict):
            src = resolve_widget_iframe_src(cfg, request=request)
            if src:
                return src

    for spec in registry_specs_for_slug(app_slug):
        if wid and spec.widget_id != wid:
            continue
        src = _resolve_url_name(
            spec.url_name,
            url_kwargs=spec.url_kwargs,
            request=request,
        )
        if src:
            return src
    return None


def registry_validation_errors(*, catalog_slugs: list[str] | None = None) -> list[str]:
    """TOP_15 explicit + full catalog slug coverage with reversible url_name."""
    from apps.marketplace.management.commands.seed_marketplace_apps import (
        FIRST_PARTY_APPS,
    )

    errors: list[str] = []
    slugs = catalog_slugs or [app["slug"] for app in FIRST_PARTY_APPS]
    missing_top = sorted(TOP_15_APP_SLUGS - set(SANDBOX_EMBED_REGISTRY.keys()))
    if missing_top:
        errors.append(f"registry missing TOP_15 slugs: {', '.join(missing_top)}")
    for slug in slugs:
        specs = registry_specs_for_slug(slug)
        if not specs:
            errors.append(f"{slug}: no embed specs")
            continue
        for spec in specs:
            if not spec.widget_id or not spec.url_name:
                errors.append(f"{slug}: incomplete spec {spec!r}")
                continue
            if _resolve_url_name(spec.url_name, url_kwargs=spec.url_kwargs) is None:
                errors.append(f"{slug}: url_name does not reverse: {spec.url_name}")
    return errors
