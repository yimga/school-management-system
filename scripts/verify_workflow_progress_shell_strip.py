#!/usr/bin/env python3
"""Workflow progress strip shell contract.

Manager control plane: strip lives in ``manager_operator_topbar`` header slot
(transitively via ``control_plane_unified_header``). Canvas body must not
duplicate the include (Render deploy + UX).

Tenant portal: direct include in ``portal_base.html``.
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


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []
    wfp = "rmc_workflow_progress_strip.html"

    portal = _read("templates/portal_base.html")
    if wfp not in portal:
        failures.append("portal_base.html: missing workflow progress strip include")

    topbar = _read("templates/partials/manager_operator_topbar.html")
    if wfp not in topbar:
        failures.append("manager_operator_topbar.html: missing workflow progress strip include")
    if "data-rmc-wfp-header-slot" not in topbar:
        failures.append("manager_operator_topbar.html: missing rmc-wfp-header-slot")

    skeleton = _read("templates/control_plane_skeleton.html")
    if "control_plane_unified_header.html" not in skeleton:
        failures.append(
            "control_plane_skeleton.html: missing control_plane_unified_header include"
        )
    if wfp in skeleton and CANVAS_BODY_DUP_RE.search(skeleton):
        failures.append(
            "control_plane_skeleton.html: duplicate workflow strip in canvas body "
            "(header slot via unified header is canonical)"
        )

    if failures:
        print("WORKFLOW_PROGRESS_SHELL_STRIP_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("WORKFLOW_PROGRESS_SHELL_STRIP_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
