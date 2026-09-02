#!/usr/bin/env python3
"""Platform-wide gate: operator activity tiers + dual-plane shell audit.

Two of this gate's assertions were measuring the word, not the behaviour:

  * rmc-cp-activity-tiers.css on templates/portal_base.html. The tenant shell
    links one minified bundle (css/portal-shell-enhanced.min.css) that contains
    this stylesheet as source 63 of 77, so the rules ship and the filename does
    not appear. Delivery now resolves through scripts/shell_css_contract.py.

  * The Tier-2 landing ticker strip. That partial is retired -- see the block
    comment at the check itself -- so the include it asserted had not existed on
    any of the three landings since 2026-08-19.

Stdlib-only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import shell_css_contract  # noqa: E402

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
        if rel != "templates/control_plane_base.html":
            finding = shell_css_contract.missing_stylesheet(rel, "rmc-cp-activity-tiers.css")
            if finding:
                findings.append(finding)
        if rel == "templates/control_plane_skeleton.html":
            if "_activity_ticker_drawer.html" not in text:
                findings.append("control_plane_skeleton.html: missing activity drawer include")
            if "rmc-cp-activity-drawer.js" not in text:
                findings.append("control_plane_skeleton.html: missing activity drawer JS")

    base = _read("templates/control_plane_base.html")
    tray_stack = _read("templates/partials/rmc_tools_tray_context_stack.html")
    if "_operator_incident_banner.html" not in tray_stack:
        findings.append("rmc_tools_tray_context_stack.html: missing Tier-3 incident banner")
    if "_operator_incident_banner.html" in base:
        findings.append("control_plane_base.html: incident banner must not render in canvas")
    if "_platform_pulse.html" in base and "cp_shell_canvas_chrome" in base:
        chrome_block = base.split("cp_shell_canvas_chrome", 1)[1][:600]
        if "_platform_pulse.html" in chrome_block:
            findings.append(
                "control_plane_base.html: platform_pulse must be landing-only, not canvas chrome"
            )

    # ---- Tier 2: the landing ticker strip ---------------------------------
    # _activity_ticker_landing_strip.html is RETIRED. It was hoisted off these
    # three operator landings into the shared header on 2026-06-06 (ae1b2cc4d:
    # "LIVE marquee row is now the DEFAULT in control_plane_unified_header.html
    # -- per-dashboard override removed to avoid a double row"), and the header
    # row itself was removed on 2026-08-19 (0711ac109, quiet-header v2:
    # "Landing-strip chrome is retired from the header stack"), which also
    # dropped it from portal_base's tenant role-home banner. Nothing includes
    # the partial today, so asserting the include asserted the pre-2026-08-19
    # contract and failed on all three landings every run.
    #
    # What replaced it is the Tier-1 inline badge plus the drawer it opens, both
    # of which every landing inherits through its shell chain -- so that is what
    # is asserted. A HALF state is a finding: some landings carrying the retired
    # strip while others do not is exactly the drift this gate exists to catch.
    strip_wired = [
        rel
        for rel in LANDING_TEMPLATES
        if shell_css_contract.renders(rel, "_activity_ticker_landing_strip.html")
    ]
    if strip_wired and len(strip_wired) != len(LANDING_TEMPLATES):
        findings.append(
            "Tier-2 landing ticker strip is half-wired: "
            + ", ".join(strip_wired)
            + " render it while the other operator landings do not"
        )
    for rel in LANDING_TEMPLATES:
        if rel in strip_wired:
            continue
        for partial in ("_activity_ticker_inline.html", "_activity_ticker_drawer.html"):
            if not shell_css_contract.renders(rel, partial):
                findings.append(
                    f"{rel}: no Tier-2 activity surface -- neither the retired "
                    f"landing strip nor {partial} is reachable from this landing"
                )

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
    if "_operator_incident_banner.html" in admin_base:
        findings.append("admin/base.html: incident banner must not render in canvas")

    portal = _read("templates/portal_base.html")
    if "tenant_role_home_landing" not in portal:
        findings.append("portal_base.html: Tier-2 landing must use tenant_role_home_landing")
    incident = _read("templates/partials/cockpit/_operator_incident_banner.html")
    if "tenant_incident_banner" not in incident:
        findings.append("incident banner partial: missing tenant_incident_banner branch")
    if portal.count("_operator_incident_banner.html") > 0:
        findings.append("portal_base.html: incident banner must not render in canvas (use Tools tray)")

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
