#!/usr/bin/env python3
"""Platform gate: vertical workspace policy on every authenticated shell."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

AUTHENTICATED_SHELLS = (
    "templates/control_plane_skeleton.html",
    "templates/portal_base.html",
    "templates/base.html",
    "templates/admin/base_site.html",
)

SHELL_INHERITANCE = (
    ("templates/control_plane_base.html", "control_plane_skeleton.html"),
    ("templates/admin/base_site.html", "admin/base.html"),
)

DENSITY_CSS = (
    "rmc-vertical-density-platform.css",
    "rmc-platform-vertical-compact.css",
)

HEAVY_CHROME_PARTIALS = (
    "_platform_pulse.html",
    "_activity_ticker.html",
)


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def main() -> int:
    findings: list[str] = []

    contract = _read("apps/platform_runtime/shell_contract.py")
    if "vertical_workspace_policy" not in contract:
        findings.append("shell_contract.py: missing vertical_workspace_policy()")
    if 'heavy_chrome_rule": "landing-only"' not in contract:
        findings.append("shell_contract.py: heavy_chrome_rule must be landing-only")

    registry = _read("templates/partials/shell_rmc_registry_html_attrs.html")
    if "data-rmc-vertical-workspace-policy" not in registry:
        findings.append("shell_rmc_registry_html_attrs.html: missing workspace policy data attr")

    for rel in AUTHENTICATED_SHELLS:
        text = _read(rel)
        for css in DENSITY_CSS:
            if css not in text:
                findings.append(f"{rel}: missing {css}")

    for child, parent in SHELL_INHERITANCE:
        child_text = _read(child)
        if f'extends "{parent}"' not in child_text and f"extends '{parent}'" not in child_text:
            findings.append(f"{child}: must extend {parent} (density CSS inheritance)")

    portal = _read("templates/portal_base.html")
    tenant_ticker_block = portal.split("portal_shell_header_ticker_tenant", 1)[1][:400]
    if "_activity_ticker.html" in tenant_ticker_block:
        findings.append(
            "portal_base.html: tenant header must not include global _activity_ticker.html"
        )
    if "portal_landing_activity_ticker" not in portal:
        findings.append("portal_base.html: missing portal_landing_activity_ticker block")
    if "tenant_role_home_landing" not in portal:
        findings.append("portal_base.html: legacy role-home Tier-2 must use tenant_role_home_landing")
    if 'data-rmc-tp-mission-surface="1"' not in portal:
        findings.append("portal_base.html: mission strip must render in tp-mission-surface (dashboard body)")
    header_chunk = portal.split("tp-primary-nav-bandrow", 1)[1].split("portal_shell_header_ticker_tenant", 1)[0]
    if "tp_mission_strip.html" in header_chunk:
        findings.append("portal_base.html: tp_mission_strip must not live in header chrome")

    inline_partial = _read("templates/partials/cockpit/_activity_ticker_inline.html")
    if "tenant_activity_ticker" not in inline_partial:
        findings.append("inline partial: missing tenant_activity_ticker Tier-1 branch")
    if "_activity_ticker_inline.html" not in portal:
        findings.append("portal_base.html: tenant Tier-1 inline badge not wired in header")

    drawer_partial = _read("templates/partials/cockpit/_activity_ticker_drawer.html")
    if "data-rmc-tenant-activity-drawer" not in drawer_partial:
        findings.append("drawer partial: missing tenant activity drawer branch")
    if "_activity_ticker_drawer.html" not in portal:
        findings.append("portal_base.html: activity drawer not included for authenticated portal")
    if "rmc-cp-activity-drawer.js" not in portal:
        findings.append("portal_base.html: activity drawer JS missing for authenticated portal")

    base = _read("templates/control_plane_base.html")
    if "_platform_pulse.html" in base and "cp_shell_canvas_chrome" in base:
        chrome_block = base.split("cp_shell_canvas_chrome", 1)[1][:600]
        if "_platform_pulse.html" in chrome_block:
            findings.append(
                "control_plane_base.html: platform_pulse must be landing-only, not canvas chrome"
            )

    landing_strip = _read("templates/partials/cockpit/_activity_ticker_landing_strip.html")
    if "data-rmc-tenant-landing-ticker" not in landing_strip:
        findings.append("landing strip: missing tenant landing ticker gate")

    stale_global_doc_markers = (
        "Rendered as global chrome at the top of every authenticated page",
        "GLOBAL live platform activity ticker",
    )
    for partial in HEAVY_CHROME_PARTIALS:
        head = _read(f"templates/partials/cockpit/{partial}")[:1200]
        for marker in stale_global_doc_markers:
            if marker in head:
                findings.append(f"cockpit/{partial}: doc still claims global header chrome")

    if findings:
        print("PLATFORM_VERTICAL_WORKSPACE_POLICY_FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("PLATFORM_VERTICAL_WORKSPACE_POLICY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
