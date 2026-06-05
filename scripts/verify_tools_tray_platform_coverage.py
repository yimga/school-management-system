#!/usr/bin/env python3
"""v4.02.17 — Tools tray + workflow chrome platform-wide coverage gate.

Ensures page-aware Tools edge-tray and tray-only workflow UI ship on every
authenticated workspace shell (operator manager host + tenant host), not only
``/super/`` routes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TRAY_STACK = "templates/partials/rmc_tools_tray_context_stack.html"

# Shell → required wiring needles (substring checks).
OPERATOR_SHELLS: dict[str, tuple[str, ...]] = {
    "templates/control_plane_skeleton.html": (
        "rmc_operator_tools_styles.html",
        "rmc_operator_tools_scripts.html",
        "rmc-assist-dock.js",
        "rmc-workflow-progress.js",
    ),
    "templates/portal_base.html": (
        "rmc_operator_tools_styles.html",
        "rmc_operator_tools_scripts.html",
        "rmc_tenant_tools_styles.html",
        "rmc_tenant_tools_scripts.html",
        "rmc-assist-dock.js",
        "rmc-workflow-progress.js",
    ),
    "templates/admin/base_site.html": (
        "rmc-assist-dock.js",
        "rmc-workflow-progress.js",
        "rmc_operator_tools_scripts.html",
        "rmc_tenant_tools_scripts.html",
    ),
}

CANVAS_FORBIDDEN_INCLUDES = (
    "components/rmc_workflow_progress_strip.html",
    "components/_workflow_auto_chrome.html",
    "partials/cockpit/_operator_incident_banner.html",
)

ALLOWLIST_FILES = frozenset(
    {
        TRAY_STACK,
        "templates/components/rmc_workflow_progress_strip.html",
        "templates/components/_workflow_auto_chrome.html",
        "templates/partials/cockpit/_operator_incident_banner.html",
        "templates/components/workflow_status_strip.html",
        "templates/components/workflow_next_action.html",
        "templates/components/workflow_help_panel.html",
        "templates/components/rmc_workflow_tenant_trust_strip.html",
    }
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _scan_canvas_leaks() -> list[str]:
    failures: list[str] = []
    templates_dir = ROOT / "templates"
    for path in sorted(templates_dir.rglob("*.html")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWLIST_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in CANVAS_FORBIDDEN_INCLUDES:
            if needle in text:
                failures.append(f"{rel}: canvas leak — {needle} must be tray-only")
    return failures


def main() -> int:
    failures: list[str] = []

    stack = _read(TRAY_STACK)
    for needle in (
        "data-rmc-tools-tray-context",
        "data-rmc-wfp-tray-slot",
        "rmc_workflow_progress_strip.html",
        "_workflow_auto_chrome.html",
    ):
        if needle not in stack:
            failures.append(f"{TRAY_STACK}: missing {needle}")

    for rel, needles in OPERATOR_SHELLS.items():
        text = _read(rel)
        for needle in needles:
            if needle not in text:
                failures.append(f"{rel}: missing {needle}")

    admin = _read("templates/admin/base_site.html")
    if "rmc_operator_tools_scripts.html" not in admin:
        failures.append("admin/base_site.html: missing manager operator tools scripts")
    if "rmc_tenant_tools_scripts.html" not in admin:
        failures.append("admin/base_site.html: missing tenant tools scripts branch")

    topbar = _read("templates/partials/manager_operator_topbar.html")
    if "rmc_workflow_progress_strip.html" in topbar:
        failures.append("manager_operator_topbar.html: workflow strip must not be in header")

    page_ctx = _read("apps/assist_dock/tools_tray_page_context.py")
    if "normalize_workspace_path" not in page_ctx:
        failures.append("tools_tray_page_context.py: missing tenant /t/ path normalization")

    quick = _read("apps/assist_dock/quick_actions.py")
    if "def normalize_workspace_path" not in quick:
        failures.append("quick_actions.py: missing normalize_workspace_path")

    js = _read("static/js/rmc-operator-tools-tray.js")
    if "data-rmc-tools-tray-context" not in js.split("isOperatorToolsSurface")[1][:600]:
        failures.append("rmc-operator-tools-tray.js: surface gate must require tray context stack")

    failures.extend(_scan_canvas_leaks())

    if failures:
        print("TOOLS_TRAY_PLATFORM_COVERAGE_FAIL", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("TOOLS_TRAY_PLATFORM_COVERAGE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
