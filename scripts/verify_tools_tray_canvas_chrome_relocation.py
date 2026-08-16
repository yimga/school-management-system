#!/usr/bin/env python3
"""v4.02.10 — Workflow guidance + incident banners must live in Tools tray only."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANVAS_SHELLS = (
    "templates/control_plane_skeleton.html",
    "templates/control_plane_base.html",
    "templates/portal_base.html",
    "templates/admin/base.html",
)

CANVAS_FORBIDDEN = (
    "components/_workflow_auto_chrome.html",
    "partials/cockpit/_operator_incident_banner.html",
    "components/workflow_status_strip.html",
    "components/workflow_next_action.html",
    "components/rmc_workflow_progress_strip.html",
)

TRAY_WIRING = (
    "templates/partials/rmc_tools_tray_context_stack.html",
    "templates/partials/rmc_operator_tools_scripts.html",
    "templates/partials/rmc_tenant_tools_scripts.html",
)

PAGE_TEMPLATES = (
    "templates/finance/cash_office_closure.html",
    "templates/accounts/rollover_year.html",
    "templates/accounts/entity_import.html",
    "templates/compliance/erasure_request.html",
    "templates/payroll/create_run.html",
    "templates/migration_cloud/connector/_wizard_base.html",
    "templates/studio_os/modes/output.html",
    "templates/parent/dashboard.html",
    "templates/parent/finance.html",
    "templates/parent/contact_school.html",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    stack = _read("templates/partials/rmc_tools_tray_context_stack.html")
    if "data-rmc-tools-tray-context" not in stack:
        failures.append("rmc_tools_tray_context_stack.html missing tray context marker")
    if "_workflow_auto_chrome.html" not in stack:
        failures.append("rmc_tools_tray_context_stack.html missing workflow auto-chrome")
    if "_operator_incident_banner.html" not in stack:
        failures.append("rmc_tools_tray_context_stack.html missing incident banner")
    if "rmc_workflow_progress_strip.html" not in stack:
        failures.append("rmc_tools_tray_context_stack.html missing workflow progress strip")
    if "data-rmc-wfp-tray-slot" not in stack:
        failures.append("rmc_tools_tray_context_stack.html missing workflow chip tray slot")

    topbar = _read("templates/partials/manager_operator_topbar.html")
    if "rmc_workflow_progress_strip.html" in topbar:
        failures.append("manager_operator_topbar.html: workflow progress must be tray-only")

    for rel in TRAY_WIRING[1:]:
        text = _read(rel)
        if "rmc_tools_tray_context_stack.html" not in text:
            failures.append(f"{rel}: must include rmc_tools_tray_context_stack.html")

    for rel in CANVAS_SHELLS:
        text = _read(rel)
        for needle in CANVAS_FORBIDDEN:
            if needle in text:
                failures.append(f"{rel}: canvas must not include {needle}")

    js = _read("static/js/rmc-operator-tools-tray.js")
    if "mountContextStack" not in js:
        failures.append("rmc-operator-tools-tray.js missing mountContextStack")
    if "applyPageContext" not in js:
        failures.append("rmc-operator-tools-tray.js missing applyPageContext")
    if "[data-rmc-tools-tray-context]" not in js:
        failures.append("rmc-operator-tools-tray.js missing universal tray context gate")

    css = _read("static/css/rmc-operator-tools-tray.css")
    if ".rmc-operator-tools__context-stack" not in css:
        failures.append("rmc-operator-tools-tray.css missing context-stack styles")
    if ".rmc-operator-tools__page-head" not in css:
        failures.append("rmc-operator-tools-tray.css missing page-head styles")

    for rel in PAGE_TEMPLATES:
        text = _read(rel)
        for needle in CANVAS_FORBIDDEN:
            if needle in text:
                failures.append(f"{rel}: inline workflow/incident chrome forbidden ({needle})")

    portal = _read("templates/portal_base.html")
    if "rmc_workflow_progress_strip.html" in portal:
        failures.append("portal_base.html: workflow progress strip must be tray-only")
    if "rmc_workflow_tenant_trust_strip.html" in portal:
        failures.append("portal_base.html: tenant trust strip must be tray-only")

    if failures:
        print("TOOLS_TRAY_CANVAS_CHROME_RELOCATION_FAIL", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("TOOLS_TRAY_CANVAS_CHROME_RELOCATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
