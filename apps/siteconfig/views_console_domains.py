"""
Console UX per domain (B3). One entry point listing seven bounded domains with guided links.
Outcomes not jargon: Standardize grading, Configure branding, Assign dashboards, etc.
"""
from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import reverse

# Seven domains (plan B1) with outcome-first labels and target views.
CONSOLE_DOMAINS = [
    {
        "code": "brand_experience",
        "name": "Brand & experience",
        "outcome": "Configure branding and themes",
        "links": [
            ("Theme & colors", "siteconfig:theme_colors"),
            ("Customizer", "siteconfig:customizer"),
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
    return render(
        request,
        "siteconfig/console_domains_hub.html",
        {"domains": CONSOLE_DOMAINS},
    )
