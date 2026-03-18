"""
Console UX per domain (B3). One entry point listing seven bounded domains with guided links.
Outcomes not jargon: Standardize grading, Configure branding, Assign dashboards, etc.
Each console supports search, preview, diff, audit, rollback where relevant (9.5/10 excellence).
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)

# Per-domain actions for 9.5/10: search, preview, diff (compare before apply), audit (change history), rollback (revert where relevant).
# Use None to hide; reverse() name or path string. Operator-safe: outcomes not jargon.
CONSOLE_ACTIONS = {
    "brand_experience": {
        "search": "studio_os:experience",
        "preview": "siteconfig:preview_from_form",
        "diff": "studio_os:experience",
        "audit": None,
        "rollback": None,
    },
    "runtime_blueprints": {
        "search": "siteconfig:dashboard_hub",
        "preview": "studio_os:automation",
        "diff": "siteconfig:dashboard_hub",
        "audit": None,
        "rollback": None,
    },
    "policies_rules": {
        "search": "siteconfig:feature_control_panel",
        "preview": "siteconfig:feature_control_audit",
        "diff": "siteconfig:feature_control_panel",
        "audit": "siteconfig:feature_control_audit",
        "rollback": None,
    },
    "plans_entitlements": {
        "search": "siteconfig:module_market",
        "preview": None,
        "diff": None,
        "audit": None,
        "rollback": None,
    },
    "global_registries": {
        "search": "siteconfig:grading_settings",
        "preview": None,
        "diff": None,
        "audit": None,
        "rollback": None,
    },
    "integrations_marketplace": {
        "search": "siteconfig:module_market",
        "preview": "siteconfig:marketplace_sandbox_embed",
        "diff": None,
        "audit": None,
        "rollback": None,
    },
    "metadata_catalog": {
        "search": "admin:metadata_entitycatalogentry_changelist",
        "preview": "admin:metadata_configmutationauditlog_changelist",
        "diff": "admin:metadata_entitycatalogentry_changelist",
        "audit": "admin:metadata_configmutationauditlog_changelist",
        "rollback": None,
    },
}

# Seven domains (plan B1) with outcome-first labels and target views.
CONSOLE_DOMAINS = [
    {
        "code": "brand_experience",
        "name": "Brand & experience",
        "outcome": "Configure branding and themes",
        "links": [
            ("Theme & colors", "siteconfig:theme_colors"),
            ("Studio", "studio_os:shell"),
            ("School theme", "siteconfig:school_theme_settings"),
            ("Brand import from URL", "siteconfig:brand_import_from_url"),
        ],
    },
    {
        "code": "runtime_blueprints",
        "name": "Runtime & blueprints",
        "outcome": "Blueprints, dashboards, workflows",
        "links": [
            ("Dashboard hub", "siteconfig:dashboard_hub"),
            ("Automation Studio", "studio_os:automation"),
            ("Output Studio", "studio_os:output"),
            ("Dashboard configuration", "siteconfig:dashboard_configuration_hub"),
            ("Report builder", "siteconfig:reportcard_builder"),
        ],
    },
    {
        "code": "policies_rules",
        "name": "Policies & rules",
        "outcome": "Feature toggles and approval rules",
        "links": [
            ("Feature control", "siteconfig:feature_control_panel"),
            ("Feature audit", "siteconfig:feature_control_audit"),
        ],
    },
    {
        "code": "plans_entitlements",
        "name": "Plans & entitlements",
        "outcome": "Plans, add-ons, waivers",
        "links": [
            ("Request waiver", "siteconfig:request_waiver"),
            ("Modules", "siteconfig:module_market"),
        ],
    },
    {
        "code": "global_registries",
        "name": "Global registries",
        "outcome": "Region, grading, calendar",
        "links": [
            ("Grading settings", "siteconfig:grading_settings"),
        ],
    },
    {
        "code": "integrations_marketplace",
        "name": "Integrations & marketplace",
        "outcome": "Integrations and app marketplace",
        "links": [
            ("Modules", "siteconfig:module_market"),
            ("App sandbox", "siteconfig:marketplace_sandbox_embed"),
        ],
    },
    {
        "code": "metadata_catalog",
        "name": "Metadata catalog",
        "outcome": "Entity/field catalog and lineage",
        "links": [
            ("Admin: Entity catalog", "admin:metadata_entitycatalogentry_changelist"),
            ("Admin: Config audit", "admin:metadata_configmutationauditlog_changelist"),
        ],
    },
]


def _safe_reverse(name: str, request=None):
    """Resolve URL by name; support admin: namespace. Returns None on NoReverseMatch and logs at debug."""
    try:
        if name.startswith("admin:"):
            return reverse(name)
        return reverse(name)
    except NoReverseMatch as e:
        logger.debug("Console domain URL name %r failed to resolve: %s", name, e)
        return None


def _build_console_domains_context(request: HttpRequest) -> list[dict[str, Any]]:
    """Build a fresh list of domain dicts with resolved URLs (no mutation of CONSOLE_DOMAINS)."""
    domains = []
    for d in CONSOLE_DOMAINS:
        resolved_links = []
        for label, name in d["links"]:
            try:
                url = reverse(name)
                resolved_links.append({"label": label, "url": url})
            except NoReverseMatch as e:
                logger.debug(
                    "Console domain %s link %r (%r) failed to resolve: %s",
                    d["code"],
                    label,
                    name,
                    e,
                )
                resolved_links.append({"label": label, "url": "#"})
        actions = CONSOLE_ACTIONS.get(d["code"], {})
        domains.append(
            {
                "code": d["code"],
                "name": d["name"],
                "outcome": d["outcome"],
                "resolved_links": resolved_links,
                "search_url": _safe_reverse(actions.get("search"))
                if actions.get("search")
                else None,
                "preview_url": _safe_reverse(actions.get("preview"))
                if actions.get("preview")
                else None,
                "diff_url": _safe_reverse(actions.get("diff"))
                if actions.get("diff")
                else None,
                "audit_url": _safe_reverse(actions.get("audit"))
                if actions.get("audit")
                else None,
                "rollback_url": _safe_reverse(actions.get("rollback"))
                if actions.get("rollback")
                else None,
            }
        )
    return domains


def _build_platform_config_context(request: HttpRequest) -> list[dict[str, Any]]:
    """Platform config cards for manager: site settings, regions, plans, feature toggles, AI. Only used on manager."""
    cards = []
    entries = [
        (
            "site_settings",
            "Site settings",
            "Platform-level site name, theme, and defaults.",
            "super:site_settings_list",
            "bi-gear",
            None,
        ),
        (
            "regions",
            "Regions & grading",
            "Region config and grading scale catalog.",
            None,
            "bi-globe",
            [
                ("Regions", "super:regions_list"),
                ("Grading", "super:grading_list"),
            ],
        ),
        (
            "plans",
            "Plans & add-ons",
            "Billing plans and add-on catalog.",
            "super:plans_list",
            "bi-currency-dollar",
            None,
        ),
        (
            "feature_toggles",
            "Feature toggles",
            "Platform feature flag definitions and state.",
            "super:feature_toggles_list",
            "bi-toggle-on",
            None,
        ),
        (
            "ai_models",
            "AI / model registry",
            "AI model registry and regional config.",
            "super:ai_model_hub",
            "bi-cpu",
            None,
        ),
    ]
    for code, name, outcome, single_url, icon, links in entries:
        resolved = []
        if single_url:
            try:
                resolved.append({"label": "Open", "url": reverse(single_url)})
            except NoReverseMatch:
                pass
        elif links:
            for label, url_name in links:
                try:
                    resolved.append({"label": label, "url": reverse(url_name)})
                except NoReverseMatch:
                    pass
        if resolved:
            cards.append(
                {
                    "code": code,
                    "name": name,
                    "outcome": outcome,
                    "icon": icon,
                    "links": resolved,
                }
            )
    return cards


def _build_operational_links_context(request: HttpRequest) -> list[dict[str, str]]:
    """Operational quick links for manager: schools, incidents, billing, migration."""
    out = []
    for label, url_name in [
        ("Schools list", "super:schools_list"),
        ("Incidents", "super:incidents_list"),
        ("Billing", "super:billing_dashboard"),
        ("Billing accounts", "super:billing_accounts_list"),
        ("Migration", "super:migration_cloud"),
        ("Migration runs", "super:migration_runs_list"),
        ("Pulse", "super:pulse"),
    ]:
        try:
            out.append({"label": label, "url": reverse(url_name)})
        except NoReverseMatch:
            pass
    return out


def _build_operational_hubs_context(request: HttpRequest) -> list[dict[str, Any]]:
    """Operational hubs merged into System config: Studio OS entry plus Workflow, Approvals, Import, Documents, Reports, RBAC, Feature control, Communications. Single integrated list."""
    hubs = []
    for label, url_name, icon in [
        ("Studio OS", "studio_os:shell", "bi-window-stack"),
        ("Workflow center", "studio_os:workflow_center", "bi-diagram-3"),
        ("Approval hub", "studio_os:approval_hub", "bi-clipboard-check"),
        ("Import & bulk", "studio_os:import_hub", "bi-upload"),
        ("Document library", "portal:document_library_manage", "bi-folder2-open"),
        ("Report library", "studio_os:output", "bi-journal-text"),
        ("RBAC & permissions", "accounts:rbac", "bi-shield-lock"),
        ("Feature control", "siteconfig:feature_control_panel", "bi-toggle-on"),
        ("Message groups", "communication:group_list", "bi-people"),
        ("Announcements", "communication:announcement_create", "bi-megaphone"),
    ]:
        url = _safe_reverse(url_name)
        if url:
            hubs.append({"label": label, "url": url, "icon": icon})
    return hubs


@staff_member_required
def console_domains_hub(request: HttpRequest) -> HttpResponse:
    """Single bounded console: operational hubs + configuration domains + (manager) platform config + operational links. Backoffice merged here; one UI."""
    domains = _build_console_domains_context(request)
    operational_hubs = _build_operational_hubs_context(request)
    studio_shell_url = _safe_reverse("studio_os:shell")
    template = (
        "siteconfig/console_domains_hub_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "siteconfig/console_domains_hub.html"
    )
    context = {
        "domains": domains,
        "operational_hubs": operational_hubs,
        "studio_shell_url": studio_shell_url,
        "studio_experience_url": _safe_reverse("studio_os:experience"),
        "guided_onboarding_url": _safe_reverse("siteconfig:guided_onboarding"),
        "theme_colors_hub_url": _safe_reverse("siteconfig:theme_colors"),
    }
    if template == "siteconfig/console_domains_hub_control_plane.html":
        try:
            context["super_dashboard_url"] = reverse("super:dashboard")
        except NoReverseMatch:
            context["super_dashboard_url"] = None
        context["platform_config"] = _build_platform_config_context(request)
        context["operational_links"] = _build_operational_links_context(request)
        try:
            context["admin_index_url"] = reverse("admin:index")
        except NoReverseMatch:
            context["admin_index_url"] = None
    return render(request, template, context)
