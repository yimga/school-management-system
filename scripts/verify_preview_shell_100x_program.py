#!/usr/bin/env python3
"""Preview Shell 100x Parity — program scaffold gate (batch 1477–1478).

Asserts canonical plan, three north-star preview HTML files, copilot rail
preservation on manager shell, and page-context help wiring. Does not claim
full parity — use verify_preview_shell_100x_completion.py after batch 1483.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PREVIEWS = (
    "docs/generated/preview_app_shell_manager_v8_200x.html",
    "docs/generated/preview_app_shell_admin_v1_200x.html",
    "docs/generated/preview_app_shell_tenant_portal_v3_100x.html",
)

SHELLS_NEED_PAGE_HELP = (
    "templates/control_plane_skeleton.html",
    "templates/portal_base.html",
    "templates/admin/base_site.html",
)


def _text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    findings: list[str] = []

    plan = ROOT / "docs/plans/PREVIEW_SHELL_100X_PARITY_PLAN.md"
    if not plan.is_file():
        findings.append("missing docs/plans/PREVIEW_SHELL_100X_PARITY_PLAN.md")
    else:
        body = plan.read_text(encoding="utf-8", errors="replace")
        for needle in ("1477", "1483", "DO NOT REFACTOR", "Aggressive build-agent prompt"):
            if needle not in body:
                findings.append(f"plan missing required section marker: {needle!r}")

    sot = _text("docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md")
    if "batch 1477" not in sot or "PREVIEW_SHELL_100X" not in sot:
        findings.append("SOT §11.4 missing batch 1477 program row")

    for rel in PREVIEWS:
        if not (ROOT / rel).is_file():
            findings.append(f"missing preview HTML: {rel}")

    impl = ROOT / "scripts/verify_all_preview_shell_html_implementation.py"
    if not impl.is_file():
        findings.append("missing scripts/verify_all_preview_shell_html_implementation.py")

    cp_skeleton = _text("templates/control_plane_skeleton.html")
    if "_ai_copilot_rail.html" not in cp_skeleton:
        findings.append(
            "control_plane_skeleton.html must include partials/cockpit/_ai_copilot_rail.html"
        )

    for rel in SHELLS_NEED_PAGE_HELP:
        body = _text(rel)
        if not body:
            findings.append(f"missing shell: {rel}")
            continue
        if "rmc-page-context-help.js" not in body:
            findings.append(f"{rel}: missing rmc-page-context-help.js")

    completion = ROOT / "scripts/verify_preview_shell_100x_completion.py"
    if not completion.is_file():
        findings.append("missing scripts/verify_preview_shell_100x_completion.py")

    registry = ROOT / "docs/generated/preview_shell_100x_parity_registry.json"
    if not registry.is_file():
        findings.append(
            "missing docs/generated/preview_shell_100x_parity_registry.json (Phase 0)"
        )

    # SOT batch IDs reserved in plan
    for batch in range(1477, 1484):
        if f"batch {batch}" not in sot:
            findings.append(f"SOT §11.4 missing batch {batch} row")

    if findings:
        print("verify_preview_shell_100x_program: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_preview_shell_100x_program: PREVIEW_SHELL_100X_PROGRAM_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
