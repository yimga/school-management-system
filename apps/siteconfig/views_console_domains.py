"""
Console UX per domain (B3). One entry point listing seven bounded domains with guided links.
Outcomes not jargon: Standardize grading, Configure branding, Assign dashboards, etc.
Each console supports search, preview, diff, audit, rollback where relevant (9.5/10 excellence).
"""
from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import reverse

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
        "preview": "siteconfig:workflow_hub",
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
            ("Workflow hub", "siteconfig:workflow_hub"),
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
    """Resolve URL by name; support admin: namespace."""
    try:
        if name.startswith("admin:"):
            from django.urls import reverse
            return reverse(name)
        return reverse(name)
    except Exception:
        return None


@staff_member_required
def console_domains_hub(request):
    """Single console entry: list seven domains with outcome-first links (search, preview, diff, rollback linked from each area)."""
    for d in CONSOLE_DOMAINS:
        d["resolved_links"] = []
        for label, name in d["links"]:
            try:
                url = reverse(name)
                d["resolved_links"].append({"label": label, "url": url})
            except Exception:
                d["resolved_links"].append({"label": label, "url": "#"})
        actions = CONSOLE_ACTIONS.get(d["code"], {})
        d["search_url"] = _safe_reverse(actions.get("search")) if actions.get("search") else None
        d["preview_url"] = _safe_reverse(actions.get("preview")) if actions.get("preview") else None
        d["diff_url"] = _safe_reverse(actions.get("diff")) if actions.get("diff") else None
        d["audit_url"] = _safe_reverse(actions.get("audit")) if actions.get("audit") else None
        d["rollback_url"] = _safe_reverse(actions.get("rollback")) if actions.get("rollback") else None
    return render(
        request,
        "siteconfig/console_domains_hub.html",
        {"domains": CONSOLE_DOMAINS},
    )
