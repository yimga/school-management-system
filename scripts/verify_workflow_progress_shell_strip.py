#!/usr/bin/env python3
"""Workflow progress strip shell contract.

v4.02.16 — Live workflow progress (chip + inline strip) lives in the Tools
edge-tray context stack only — not manager header or page canvas.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANVAS_BODY_DUP_RE = re.compile(
    r'data-rmc-cp-page-body="1"[\s\S]{0,6000}?rmc_workflow_progress_strip\.html',
    re.MULTILINE,
)

TRAY_STACK = "templates/partials/rmc_tools_tray_context_stack.html"
WFP = "rmc_workflow_progress_strip.html"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []

    stack = _read(TRAY_STACK)
    if WFP not in stack:
        failures.append(f"{TRAY_STACK}: missing workflow progress strip include")
    if "data-rmc-wfp-tray-slot" not in stack:
        failures.append(f"{TRAY_STACK}: missing data-rmc-wfp-tray-slot mount point")

    topbar = _read("templates/partials/manager_operator_topbar.html")
    if WFP in topbar:
        failures.append("manager_operator_topbar.html: workflow strip must not render in header")
    if "data-rmc-wfp-header-slot" in topbar:
        failures.append("manager_operator_topbar.html: header workflow slot retired (tray-only)")

    portal = _read("templates/portal_base.html")
    if WFP in portal:
        failures.append("portal_base.html: workflow strip must be tray-only (not canvas)")

    skeleton = _read("templates/control_plane_skeleton.html")
    if WFP in skeleton and CANVAS_BODY_DUP_RE.search(skeleton):
        failures.append(
            "control_plane_skeleton.html: duplicate workflow strip in canvas body"
        )

    wfp_js = _read("static/js/rmc-workflow-progress.js")
    if "data-rmc-wfp-tray-slot" not in wfp_js:
        failures.append("rmc-workflow-progress.js: missing tray slot mount")

    if failures:
        print("WORKFLOW_PROGRESS_SHELL_STRIP_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("WORKFLOW_PROGRESS_SHELL_STRIP_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
