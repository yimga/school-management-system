#!/usr/bin/env python3
"""Verify nav sidebar rail + resize wiring platform-wide."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _scan_templates(pattern: str) -> list[Path]:
    rx = re.compile(pattern)
    hits: list[Path] = []
    for path in TEMPLATES.rglob("*.html"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if rx.search(text):
            hits.append(path.relative_to(ROOT))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    failures: list[str] = []

    skeleton = _read("templates/control_plane_skeleton.html")
    cp_base = _read("templates/control_plane_base.html")
    admin_base = _read("templates/admin/base.html")
    admin_site = _read("templates/admin/base_site.html")
    portal = _read("templates/portal_base.html")
    zero_ticket = _read("templates/siteconfig/zero_ticket_shell.html")
    portal_sidebar = _read("templates/partials/portal_sidebar.html")
    page_data = _read("templates/partials/rmc_nav_sidebar_page_data.html")
    js = _read("static/js/rmc-nav-sidebar.js")
    css = _read("static/css/rmc-nav-sidebar.css")
    bootstrap = _read("static/js/portal-shell-bootstrap.js")
    cockpit = _read("apps/siteconfig/cockpit_manager_200x.py")

    for needle in (
        "rmc-nav-sidebar.css",
        "rmc-nav-sidebar.js",
        "rmc_nav_sidebar_page_data.html",
        "rmc-nav-sidebar-host",
        "rmc_nav_sidebar_resize_handle.html",
    ):
        if needle not in skeleton:
            failures.append(f"control_plane_skeleton.html missing {needle}")

    for needle in (
        "rmc-nav-sidebar__mount",
        "rmc_nav_sidebar_toolbar.html",
        'id="cp-sidebar-col"',
        "rmc-shell-canvas-container",
    ):
        if needle not in cp_base:
            failures.append(f"control_plane_base.html missing {needle}")

    for needle in (
        "rmc-nav-sidebar-host",
        "rmc_nav_sidebar_toolbar.html",
        "rmc_nav_sidebar_resize_handle.html",
        'id="cp-sidebar-col"',
    ):
        if needle not in admin_base:
            failures.append(f"admin/base.html manager sidebar missing {needle}")

    for needle in (
        "rmc-nav-sidebar.css",
        "rmc-nav-sidebar.js",
        "rmc_nav_sidebar_page_data.html",
    ):
        if needle not in admin_site:
            failures.append(f"admin/base_site.html missing {needle}")

    for needle in (
        "rmc-nav-sidebar.css",
        "rmc-nav-sidebar.js",
        "rmc_nav_sidebar_page_data.html",
        "rmc_nav_sidebar_toolbar.html",
        "rmc-shell-canvas-container",
    ):
        if needle not in portal:
            failures.append(f"portal_base.html missing {needle}")
    if "portal-resize-handle" in portal:
        failures.append("portal_base.html still ships legacy portal-resize-handle")
    if "portal-resize-keyboard.js" in portal:
        failures.append("portal_base.html still ships legacy portal-resize-keyboard.js")

    for needle in (
        'id="cp-sidebar-col"',
        "rmc-nav-sidebar__mount",
        "rmc_nav_sidebar_toolbar.html",
    ):
        if needle not in zero_ticket:
            failures.append(f"zero_ticket_shell.html missing {needle}")

    if "portal-sidebar-collapse-wrap" in portal_sidebar:
        failures.append("portal_sidebar.html still ships duplicate legacy collapse wrap")

    legacy_resize_templates = _scan_templates(r"portal-resize-handle|portal-resize-keyboard\.js")
    if legacy_resize_templates:
        failures.append(
            "legacy portal resize still referenced in: "
            + ", ".join(str(p) for p in legacy_resize_templates[:8])
        )

    sidebar_override_templates = [
        p
        for p in _scan_templates(r"block cp_shell_sidebar")
        if p.as_posix()
        not in (
            "templates/control_plane_base.html",
            "templates/control_plane_skeleton.html",
            "templates/auth/admin_login.html",
            "templates/auth/manager_login.html",
            "templates/siteconfig/zero_ticket_shell.html",
        )
    ]
    if sidebar_override_templates:
        failures.append(
            "unexpected cp_shell_sidebar overrides (must use mount contract): "
            + ", ".join(str(p) for p in sidebar_override_templates[:8])
        )

    if "page-data-rmc-nav-sidebar" not in page_data:
        failures.append("rmc_nav_sidebar_page_data.html missing JSON island id")
    if "default_width" not in page_data:
        failures.append("rmc_nav_sidebar_page_data.html missing default_width cascade")

    if "data-rmc-nav-sidebar" not in js:
        failures.append("rmc-nav-sidebar.js missing data-rmc-nav-sidebar contract")
    if "rmc:shell-layout" not in js:
        failures.append("rmc-nav-sidebar.js missing rmc:shell-layout event")
    if "portal-sidebar-col" not in js:
        failures.append("rmc-nav-sidebar.js missing portal-sidebar-col support")

    for needle in (
        ".rmc-nav-sidebar__resize-handle",
        "rmc-canvas-adaptive-grid",
        "rmc-shell-canvas-container",
        "cp-overview-grid",
        "container-name: rmc-shell-canvas",
    ):
        if needle not in css:
            failures.append(f"rmc-nav-sidebar.css missing platform rule {needle!r}")

    if "portal-resize-handle" in bootstrap or "portal-sidebar-collapsed" in bootstrap:
        failures.append("portal-shell-bootstrap.js still owns legacy sidebar resize/collapse")

    if "nav_sidebar" not in cockpit or "_nav_sidebar_defaults" not in cockpit:
        failures.append("cockpit_manager_200x.py missing nav_sidebar defaults")

    orphan_kb = ROOT / "static/js/portal-resize-keyboard.js"
    if orphan_kb.is_file():
        failures.append("orphan static/js/portal-resize-keyboard.js must be deleted (superseded by rmc-nav-sidebar.js)")

    smoke = ROOT / "scripts/smoke_nav_sidebar.py"
    if not smoke.is_file():
        failures.append("scripts/smoke_nav_sidebar.py missing")
    elif "NAV_SIDEBAR_SMOKE_PASS" not in smoke.read_text(encoding="utf-8"):
        failures.append("smoke_nav_sidebar.py missing NAV_SIDEBAR_SMOKE_PASS marker")

    cp_sidebar = _read("templates/partials/control_plane_sidebar.html")
    if "data-rmc-smart-sidebar=" not in cp_sidebar:
        failures.append("control_plane_sidebar.html missing data-rmc-smart-sidebar")
    if "data-rmc-badge-poll" not in cp_sidebar:
        failures.append("control_plane_sidebar.html missing operator badge poll URL")
    if "data-rmc-smart-sidebar=" not in portal_sidebar:
        failures.append("portal_sidebar.html missing data-rmc-smart-sidebar")
    if "rmc-sidebar-intelligence.js" not in portal:
        failures.append("portal_base.html missing rmc-sidebar-intelligence.js")
    intel_js = _read("static/js/rmc-sidebar-intelligence.js")
    if "buildFrequent" not in intel_js or "liveBadges" not in intel_js:
        failures.append("rmc-sidebar-intelligence.js missing Phase 1 capabilities")
    if "rmc-sb-frequent" not in _read("static/css/rmc-class-grammar.css"):
        failures.append("rmc-class-grammar.css missing intelligent sidebar grammar")

    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    # ---------- v4.02.7 visual integrity ----------
    if re.search(r"clamp\(16rem,\s*18vw,\s*20rem\)", _read("static/css/manager-control-plane.css")):
        failures.append("manager-control-plane.css still uses fixed clamp sidebar grid (must use --portal-sidebar-width)")

    if "Sidebar visual integrity" not in css:
        failures.append("rmc-nav-sidebar.css missing v4.02.7 integrity block")

    if "col-lg-3 col-xl-2" in portal and "rmc-nav-sidebar__mount" in portal:
        failures.append("portal_base.html sidebar mount still uses Bootstrap width cols (col-lg-3 col-xl-2)")

    if "cp-sidebar-inner cp-sidebar-inner--surface p-2 rounded" in portal:
        failures.append("portal_base.html manager sidebar still uses rounded double-wrap inner shell")

    portal_head = portal.split("</head>", 1)[0]
    dual_plane_pos = portal_head.rfind("rmc_theme_experience_dual_plane_styles.html")
    nav_css_pos = portal_head.rfind("rmc-nav-sidebar.css")
    if dual_plane_pos == -1 or nav_css_pos == -1 or nav_css_pos < dual_plane_pos:
        failures.append("portal_base.html must load rmc-nav-sidebar.css after terminal dual-plane include in <head>")

    skeleton_head = skeleton.split("</head>", 1)[0]
    sk_dual = skeleton_head.rfind("rmc_theme_experience_dual_plane_styles.html")
    sk_nav = skeleton_head.rfind("rmc-nav-sidebar.css")
    if sk_dual == -1 or sk_nav == -1 or sk_nav < sk_dual:
        failures.append("control_plane_skeleton.html must load rmc-nav-sidebar.css after dual-plane include")

    admin_extrastyle = admin_site.split("{% block extrastyle %}", 1)[-1].split("{% endblock %}", 1)[0]
    ad_dual = admin_extrastyle.rfind("rmc_theme_experience_dual_plane_styles.html")
    ad_nav = admin_extrastyle.rfind("rmc-nav-sidebar.css")
    if ad_dual == -1 or ad_nav == -1 or ad_nav < ad_dual:
        failures.append("admin/base_site.html must load rmc-nav-sidebar.css after dual-plane include in extrastyle")

    if 'class="cp-sidebar-inner cp-sidebar-inner--surface d-flex flex-column flex-grow-1 min-h-0 p-2"' not in zero_ticket:
        failures.append("zero_ticket_shell.html missing cp-sidebar-inner scroll wrapper")

    luxury = _read("static/css/rmc-sidebar-luxury-10x.css")
    if "rmc-nav-sidebar__mount > .tp-sidebar-inner" not in luxury or "mask-image: none" not in luxury:
        failures.append("rmc-sidebar-luxury-10x.css missing nav-sidebar mount mask disable rule")

    backend_parity = _read("static/css/backend-shell-parity.css")
    if re.search(r"portal-sidebar-col\.portal-sidebar-collapsed\s*\{[^}]*72px", backend_parity):
        failures.append("backend-shell-parity.css still uses legacy 72px collapsed sidebar width")

    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    print("OK: nav sidebar platform contract verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
