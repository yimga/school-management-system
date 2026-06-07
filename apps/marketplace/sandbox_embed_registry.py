"""
Sandbox embed URL registry for TOP_15 marketplace catalog apps.

Widget configs store ``url_name`` (+ optional kwargs); ``sandbox_embed`` resolves
to a tenant-safe iframe src at request time (same-origin relative paths).
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
            url_name="school_security",
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


def registry_specs_for_slug(slug: str) -> tuple[SandboxEmbedSpec, ...]:
    return SANDBOX_EMBED_REGISTRY.get((slug or "").strip(), ())


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
    if slug not in TOP_15_APP_SLUGS:
        return base
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


def registry_validation_errors() -> list[str]:
    """Static checks: TOP_15 coverage + reversible url_name entries."""
    errors: list[str] = []
    missing_slugs = sorted(TOP_15_APP_SLUGS - set(SANDBOX_EMBED_REGISTRY.keys()))
    if missing_slugs:
        errors.append(f"registry missing TOP_15 slugs: {', '.join(missing_slugs)}")
    for slug, specs in sorted(SANDBOX_EMBED_REGISTRY.items()):
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
