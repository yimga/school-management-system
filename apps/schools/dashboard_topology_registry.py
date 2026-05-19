# -*- coding: utf-8 -*-
"""
Canonical dual-dashboard route registry for audits and seed validation.

Operational vs configuration tiers are enforced in dashboard_rbac.py middleware;
this module is the mechanical source of truth for verifiers and seed commands.
"""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse

# Super paths that are configuration engines (belong in /configuration/ or /admin/).
PLATFORM_SUPER_CONFIGURATION_PATH_PREFIXES: tuple[str, ...] = (
    "/super/site-settings",
    "/super/regions",
    "/super/grading",
    "/super/plans",
    "/super/feature-toggles",
    "/super/runtime",
    "/super/ai-model-hub",
)

# Default operational quick links for PlatformOperatorSuperDashboardLink seed.
DEFAULT_OPERATIONAL_SUPER_DASHBOARD_LINKS: tuple[tuple[str, str, str, int], ...] = (
    ("command-center", "Queues & command center", "/super/command-center/", 10),
    ("tenant-health", "Tenant health", "/super/tenant-health/", 20),
    ("billing-dashboard", "Billing overview", "/super/billing/", 30),
    ("migration-cloud", "Migration Cloud", "/super/migration/", 40),
    ("marketplace-governance", "Marketplace governance", "/super/marketplace/", 50),
    ("security-hub", "Security hub", "/super/security/", 60),
    ("support-dashboard", "Support", "/super/support/", 70),
)

SURFACE_TIER_OPERATIONAL = "operational"
SURFACE_TIER_CONFIGURATION = "configuration"
SURFACE_TIER_CHOICES = (
    (SURFACE_TIER_OPERATIONAL, "Operational (day-to-day)"),
    (SURFACE_TIER_CONFIGURATION, "Configuration (deep system state)"),
)


def href_is_configuration_tier(href: str) -> bool:
    """True when href targets platform or tenant configuration surfaces."""
    path = (href or "").strip().lower()
    if not path:
        return False
    if path.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        path = urlparse(path).path or path
    if path.startswith(("/configuration/", "/admin/", "/internal-admin/")):
        return True
    if path.startswith("/siteconfig/") and not path.startswith(
        ("/siteconfig/preferences", "/siteconfig/api/tour-")
    ):
        return True
    return any(path.startswith(p) for p in PLATFORM_SUPER_CONFIGURATION_PATH_PREFIXES)


def filter_operational_dashboard_links(links) -> list:
    """Drop configuration-tier rows from super-dashboard curated link querysets."""
    return [
        link
        for link in links
        if getattr(link, "surface_tier", SURFACE_TIER_OPERATIONAL)
        == SURFACE_TIER_OPERATIONAL
        and not href_is_configuration_tier(getattr(link, "href", "") or "")
    ]


def build_dashboard_topology_audit_matrix() -> dict[str, Any]:
    """Machine-readable rows for verify_dashboard_topology_integrity.py --write."""
    from apps.schools.super_admin_paired_surfaces import build_surface_parity_matrix

    spine = build_surface_parity_matrix()
    route_rows = []
    for slug, _label, path, _order in DEFAULT_OPERATIONAL_SUPER_DASHBOARD_LINKS:
        row = {
            "slug": slug,
            "path": path,
            "tier": SURFACE_TIER_OPERATIONAL,
            "config_leak": href_is_configuration_tier(path),
            "ok": not href_is_configuration_tier(path),
        }
        route_rows.append(row)

    config_prefix_rows = [
        {
            "prefix": prefix,
            "tier": SURFACE_TIER_CONFIGURATION,
            "ok": True,
        }
        for prefix in PLATFORM_SUPER_CONFIGURATION_PATH_PREFIXES
    ]

    paired_config_on_super = []
    for spec in (
        __import__(
            "apps.schools.super_admin_paired_surfaces",
            fromlist=["SUPER_FIRST_PAIRED_SPECS"],
        ).SUPER_FIRST_PAIRED_SPECS
    ):
        super_url = (spec.get("super_url_name") or "").strip()
        path = None
        if super_url:
            try:
                path = reverse(super_url)
            except NoReverseMatch:
                path = None
        is_config = bool(super_url) and super_url in {
            "super:site_settings_list",
            "super:regions_list",
            "super:grading_list",
            "super:plans_list",
            "super:feature_toggles_list",
            "super:ai_model_hub",
        }
        paired_config_on_super.append(
            {
                "slug": spec.get("slug"),
                "super_url_name": super_url or None,
                "path": path,
                "configuration_tier": is_config,
                "has_admin_bridge": bool(spec.get("bridge_key")),
                "ok": True,
            }
        )

    operational_ok = all(r["ok"] for r in route_rows)
    return {
        "version": "2026.05.19.1",
        "surface_parity": spine,
        "default_operational_links": route_rows,
        "super_config_prefixes": config_prefix_rows,
        "super_first_pairs": paired_config_on_super,
        "operational_links_ok": operational_ok,
        "spine_ok": bool(spine.get("spine_ok")),
        "ok": operational_ok and bool(spine.get("spine_ok")),
    }
