#!/usr/bin/env python3
"""
Platform-wide activity tiers + vertical workspace audit.

Covers operator, tenant, and future-tenant authenticated shells — nothing assumed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import shell_css_contract  # noqa: E402

SUBPROCESS_GATES = (
    "scripts/verify_platform_vertical_workspace_policy.py",
    "scripts/verify_cp_consolidated_operator_shell.py",
)

INLINE_PARTIAL = "templates/partials/cockpit/_activity_ticker_inline.html"
DRAWER_PARTIAL = "templates/partials/cockpit/_activity_ticker_drawer.html"
LANDING_STRIP = "templates/partials/cockpit/_activity_ticker_landing_strip.html"

OPERATOR_SHELLS = (
    "templates/control_plane_skeleton.html",
    "templates/control_plane_base.html",
    "templates/admin/base_site.html",
    "templates/admin/base.html",
)

PORTAL = "templates/portal_base.html"


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _run_gate(rel: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(REPO / rel)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = out[-1] if out else f"exit {proc.returncode}"
    return proc.returncode == 0, summary


def main() -> int:
    findings: list[str] = []

    for gate in SUBPROCESS_GATES:
        ok, summary = _run_gate(gate)
        if not ok:
            findings.append(f"subprocess gate failed: {gate} ({summary})")

    inline = _read(INLINE_PARTIAL)
    if "data-rmc-tenant-ticker-inline" not in inline:
        findings.append(f"{INLINE_PARTIAL}: missing tenant Tier-1 inline branch")
    if "tenant_activity_ticker.cards" not in inline:
        findings.append(f"{INLINE_PARTIAL}: must read tenant_activity_ticker.cards")
    if 'data-bs-target="#rmcCpActivityDrawer"' not in inline:
        findings.append(f"{INLINE_PARTIAL}: inline badge must open activity drawer")

    drawer = _read(DRAWER_PARTIAL)
    if "data-rmc-tenant-activity-drawer" not in drawer:
        findings.append(f"{DRAWER_PARTIAL}: missing tenant drawer branch")
    if "Live school activity" not in drawer:
        findings.append(f"{DRAWER_PARTIAL}: missing tenant drawer title")

    landing = _read(LANDING_STRIP)
    if "data-rmc-tenant-landing-ticker" not in landing:
        findings.append(f"{LANDING_STRIP}: missing tenant Tier-2 landing gate")

    portal = _read(PORTAL)
    if "_activity_ticker_inline.html" not in portal:
        findings.append(f"{PORTAL}: tenant header must include Tier-1 inline partial")
    # The tenant shell links ONE minified bundle that carries this stylesheet as
    # source 63 of 77, so the filename appears nowhere in the template while the
    # rules ship on every tenant page. Both of these substring tests were the
    # same false positive, counted twice.
    tiers_finding = shell_css_contract.missing_stylesheet(PORTAL, "rmc-cp-activity-tiers.css")
    if tiers_finding:
        findings.append(tiers_finding)
    if "_activity_ticker_drawer.html" not in portal or "rmc-cp-activity-drawer.js" not in portal:
        findings.append(f"{PORTAL}: authenticated portal must include drawer + JS")
    if "portal_landing_activity_ticker" not in portal:
        findings.append(f"{PORTAL}: missing portal_landing_activity_ticker block")
    if "tenant_role_home_landing" not in portal:
        findings.append(f"{PORTAL}: Tier-2 landing must key off tenant_role_home_landing")

    incident = _read("templates/partials/cockpit/_operator_incident_banner.html")
    if "tenant_incident_banner" not in incident:
        findings.append("incident banner partial: missing tenant_incident_banner branch")

    os_strip = _read("templates/components/rmc_os_status_strip.html")
    if "tenant_incident_banner" not in os_strip or "operator_incident_banner" not in os_strip:
        findings.append(
            "rmc_os_status_strip.html: must dedupe platform_status_strip when Tier-3 shows"
        )

    tenant_ticker_block = portal.split("portal_shell_header_ticker_tenant", 1)[1][:400]
    if "_activity_ticker.html" in tenant_ticker_block:
        findings.append(f"{PORTAL}: tenant header must not include global marquee partial")

    for rel in OPERATOR_SHELLS:
        text = _read(rel)
        if rel == "templates/control_plane_base.html":
            if "_platform_pulse.html" in text and "cp_shell_canvas_chrome" in text:
                chrome = text.split("cp_shell_canvas_chrome", 1)[1][:600]
                if "_platform_pulse.html" in chrome:
                    findings.append(f"{rel}: platform_pulse must be landing-only")
        if rel in ("templates/control_plane_skeleton.html",):
            skeleton_finding = shell_css_contract.missing_stylesheet(
                rel, "rmc-cp-activity-tiers.css"
            )
            if skeleton_finding:
                findings.append(skeleton_finding)
            if "_activity_ticker_drawer.html" not in text:
                findings.append(f"{rel}: missing activity drawer include")
            if "rmc-cp-activity-drawer.js" not in text:
                findings.append(f"{rel}: missing activity drawer JS")

    admin_finding = shell_css_contract.missing_stylesheet(
        "templates/admin/base_site.html", "rmc-cp-activity-tiers.css"
    )
    if admin_finding:
        findings.append(admin_finding)

    admin_base = _read("templates/admin/base.html")
    if "_activity_ticker_drawer.html" not in admin_base:
        findings.append("admin/base.html: missing activity drawer include")
    if "rmc-cp-activity-drawer.js" not in admin_base:
        findings.append("admin/base.html: missing activity drawer JS")

    contract = _read("apps/platform_runtime/shell_contract.py")
    if "vertical_workspace_policy" not in contract:
        findings.append("shell_contract.py: missing vertical_workspace_policy()")

    ctx = _read("apps/siteconfig/cockpit_context.py")
    if not (REPO / "apps/siteconfig/cockpit_incident_banner.py").is_file():
        findings.append("missing apps/siteconfig/cockpit_incident_banner.py")
    incident_mod = _read("apps/siteconfig/cockpit_incident_banner.py")
    if "resolve_tenant_incident_banner" not in incident_mod:
        findings.append("cockpit_incident_banner.py: missing resolve_tenant_incident_banner")
    if "platform_incident" not in incident_mod:
        findings.append("cockpit_incident_banner.py: must use PlatformIncident strip")
    if "raw_tat_explicit_disabled" not in ctx:
        findings.append("cockpit_context.py: missing legacy tenant ticker opt-out migration")
    if "_pick_tenant_incident_banner" not in ctx:
        findings.append("cockpit_context.py: missing _pick_tenant_incident_banner")
    if "tenant_incident_banner" not in ctx:
        findings.append("cockpit_context.py: tenant_incident_banner not exported")

    os_strip = _read("templates/components/rmc_os_status_strip.html")
    if "tenant_incident_banner" not in os_strip or "operator_incident_banner" not in os_strip:
        findings.append(
            "rmc_os_status_strip.html: must dedupe platform_status_strip when Tier-3 shows"
        )

    registry = _read("templates/partials/shell_rmc_registry_html_attrs.html")
    if "data-rmc-vertical-workspace-policy" not in registry:
        findings.append("shell registry: missing data-rmc-vertical-workspace-policy")

    # Tier 1 opens the drawer; Tier 2 on the operator landings.
    #
    # _activity_ticker_landing_strip.html is RETIRED: hoisted off these three
    # landings into the shared header on 2026-06-06 (ae1b2cc4d), then removed
    # from the header itself on 2026-08-19 (0711ac109, quiet-header v2:
    # "Landing-strip chrome is retired from the header stack"). Nothing includes
    # it today, so this loop asserted the pre-2026-08-19 contract and failed on
    # all three landings every run. What replaced it is the Tier-1 inline badge
    # plus the drawer it opens, inherited through each landing's shell chain --
    # so that is what is asserted, with a half-wired revival as the finding.
    landings = (
        "templates/schools/super_dashboard.html",
        "templates/super/founder_dashboard.html",
        "templates/customersuccess/super_dashboard.html",
    )
    strip_wired = [
        rel
        for rel in landings
        if shell_css_contract.renders(rel, "_activity_ticker_landing_strip.html")
    ]
    if strip_wired and len(strip_wired) != len(landings):
        findings.append(
            "operator Tier-2 landing strip is half-wired: "
            + ", ".join(strip_wired)
            + " render it while the other operator landings do not"
        )
    for landing in landings:
        if landing in strip_wired:
            continue
        for partial in ("_activity_ticker_inline.html", "_activity_ticker_drawer.html"):
            if not shell_css_contract.renders(landing, partial):
                findings.append(
                    f"{landing}: no operator Tier-2 activity surface -- neither the "
                    f"retired landing strip nor {partial} is reachable"
                )

    if findings:
        print("PLATFORM_ACTIVITY_TIERS_FULL_AUDIT_FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("PLATFORM_ACTIVITY_TIERS_FULL_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
