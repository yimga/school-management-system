#!/usr/bin/env python3
"""Platform-wide gate: operator activity tiers + dual-plane shell audit."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

TIER_PARTIALS = (
    "templates/partials/cockpit/_activity_ticker_inline.html",
    "templates/partials/cockpit/_activity_ticker_landing_strip.html",
    "templates/partials/cockpit/_activity_ticker_drawer.html",
    "templates/partials/cockpit/_operator_incident_banner.html",
)

TIER_ASSETS = (
    "static/css/rmc-cp-activity-tiers.css",
    "static/js/rmc-cp-activity-drawer.js",
)

MANAGER_SHELLS = (
    "templates/control_plane_skeleton.html",
    "templates/control_plane_base.html",
    "templates/portal_base.html",
    "templates/admin/base_site.html",
)

LANDING_TEMPLATES = (
    "templates/schools/super_dashboard.html",
    "templates/super/founder_dashboard.html",
    "templates/customersuccess/super_dashboard.html",
)

DUAL_PLANE_MARKERS = (
    "rmc-theme-experience-dual-plane.css",
    "rmc_theme_experience_dual_plane_styles.html",
)


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def main() -> int:
    findings: list[str] = []

    for rel in TIER_PARTIALS + TIER_ASSETS:
        if not (REPO / rel).is_file():
            findings.append(f"missing {rel}")

    inline = _read(TIER_PARTIALS[0]) if (REPO / TIER_PARTIALS[0]).is_file() else ""
    if inline and "data-bs-target=\"#rmcCpActivityDrawer\"" not in inline:
        findings.append("inline ticker must open activity drawer (Tier 1)")

    drawer = _read(TIER_PARTIALS[2]) if (REPO / TIER_PARTIALS[2]).is_file() else ""
    if drawer and "rmcCpActivityDrawer" not in drawer:
        findings.append("activity drawer partial missing offcanvas id")

    ctx = _read("apps/siteconfig/cockpit_context.py")
    if "_pick_operator_incident_banner" not in ctx:
        findings.append("cockpit_context.py: missing _pick_operator_incident_banner")
    if "_pick_tenant_incident_banner" not in ctx:
        findings.append("cockpit_context.py: missing _pick_tenant_incident_banner")
    if "tenant_incident_banner" not in ctx:
        findings.append("cockpit_context.py: tenant_incident_banner not exported")
    if "operator_incident_banner" not in ctx:
        findings.append("cockpit_context.py: operator_incident_banner not exported")

    for rel in MANAGER_SHELLS:
        text = _read(rel)
        if "rmc-cp-activity-tiers.css" not in text and rel != "templates/control_plane_base.html":
            findings.append(f"{rel}: missing rmc-cp-activity-tiers.css")
        if rel == "templates/control_plane_skeleton.html":
            if "_activity_ticker_drawer.html" not in text:
                findings.append("control_plane_skeleton.html: missing activity drawer include")
            if "rmc-cp-activity-drawer.js" not in text:
                findings.append("control_plane_skeleton.html: missing activity drawer JS")

    base = _read("templates/control_plane_base.html")
    if "_operator_incident_banner.html" not in base:
        findings.append("control_plane_base.html: missing Tier-3 incident banner")
    if "_platform_pulse.html" in base and "cp_shell_canvas_chrome" in base:
        chrome_block = base.split("cp_shell_canvas_chrome", 1)[1][:600]
        if "_platform_pulse.html" in chrome_block:
            findings.append(
                "control_plane_base.html: platform_pulse must be landing-only, not canvas chrome"
            )

    for rel in LANDING_TEMPLATES:
        if "_activity_ticker_landing_strip.html" not in _read(rel):
            findings.append(f"{rel}: missing Tier-2 landing ticker strip")

    skeleton = _read("templates/control_plane_skeleton.html")
    if not any(marker in skeleton for marker in DUAL_PLANE_MARKERS):
        findings.append("control_plane_skeleton.html: dual-plane theme CSS not loaded")

    dual_plane = _read("static/css/rmc-theme-experience-dual-plane.css")
    if "Footer follows canvas theme" not in dual_plane:
        findings.append("dual-plane CSS: footer section missing")

    consolidated = _read("static/css/rmc-cp-consolidated-operator-shell.css")
    if "--cp-chrome-surface" not in consolidated and "cp-chrome-hairline" not in consolidated:
        findings.append("consolidated shell CSS: header inline badge not chrome-scoped")

    portal = _read("templates/portal_base.html")
    if "_activity_ticker_drawer.html" not in portal:
        findings.append("portal_base.html: missing activity drawer include")
    if "rmc-cp-activity-drawer.js" not in portal:
        findings.append("portal_base.html: missing activity drawer JS")
    if "_activity_ticker_inline.html" not in portal:
        findings.append("portal_base.html: missing tenant Tier-1 inline badge")
    inline = _read(TIER_PARTIALS[0])
    if "data-rmc-tenant-ticker-inline" not in inline:
        findings.append("inline ticker: missing tenant Tier-1 branch")
    drawer = _read(TIER_PARTIALS[2])
    if "data-rmc-tenant-activity-drawer" not in drawer:
        findings.append("activity drawer: missing tenant branch")

    admin_base = _read("templates/admin/base.html")
    if "_operator_incident_banner.html" not in admin_base:
        findings.append("admin/base.html: manager host missing incident banner")

    portal = _read("templates/portal_base.html")
    if "tenant_role_home_landing" not in portal:
        findings.append("portal_base.html: Tier-2 landing must use tenant_role_home_landing")
    incident = _read("templates/partials/cockpit/_operator_incident_banner.html")
    if "tenant_incident_banner" not in incident:
        findings.append("incident banner partial: missing tenant_incident_banner branch")
    if portal.count("_operator_incident_banner.html") < 1:
        findings.append("portal_base.html: incident banner must render for authenticated users")

    tenant_defaults = _read("apps/siteconfig/cockpit_tenant_dashboard.py")
    start = tenant_defaults.find("def _tenant_activity_ticker_defaults")
    fn_chunk = tenant_defaults[start : start + 1200] if start >= 0 else ""
    if '"enabled": True' not in fn_chunk:
        findings.append("tenant_activity_ticker defaults must enable ticker by default")

    # Re-run consolidated shell gate inline
    if "control_plane_unified_header.html" not in base:
        findings.append("control_plane_base.html: missing unified header")

    if findings:
        print("CP_OPERATOR_ACTIVITY_TIERS_PLATFORM_AUDIT_FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("CP_OPERATOR_ACTIVITY_TIERS_PLATFORM_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
