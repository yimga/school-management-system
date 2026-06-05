#!/usr/bin/env python3
"""CEZGP batch 1520 — Customer experience ease-layer gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "apps" / "siteconfig" / "command_bar_registry.py"


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


def _registry_needles() -> list[str]:
    return [
        "Import students (CSV)",
        "portal:link_child",
        "portal:claim_invite",
        "portal:parent_finance_pay_all",
        "portal:teacher_attendance_export",
        "studio_os:import_hub",
        "finance:generate_fees",
        "feedback:help_center",
        "studio_os:shell",
    ]


def main() -> int:
    failures: list[str] = []

    text = ""
    if not REGISTRY.is_file():
        failures.append("command_bar_registry.py missing")
    else:
        text = REGISTRY.read_text(encoding="utf-8", errors="replace")
        for needle in _registry_needles():
            if needle not in text:
                failures.append(f"command bar missing {needle}")

    ease_action_count = text.count('"navigate",') if text else 0
    if ease_action_count < 20:
        failures.append(f"command bar navigate actions too few ({ease_action_count})")

    if not _contains("templates/partials/rmc_tools_tray_context_stack.html", "_workflow_auto_chrome.html"):
        failures.append("tools tray context stack missing workflow auto-chrome")
    if not _contains("templates/partials/rmc_tenant_tools_scripts.html", "rmc_tools_tray_context_stack.html"):
        failures.append("tenant tools scripts missing context stack partial")
    if not _contains("templates/parent/finance.html", "data-rmc-offline-form"):
        failures.append("finance.html missing data-rmc-offline-form")
    if not _contains("templates/parent/finance_pay_all_confirm.html", "data-rmc-offline-form"):
        failures.append("finance_pay_all_confirm.html missing data-rmc-offline-form")
    if not _contains("apps/platform_runtime/workflow_registry.py", "parent-portal-contact-school"):
        failures.append("workflow_registry missing parent-portal-contact-school")

    if not _contains("templates/portal_base.html", "rmc-friction.js"):
        failures.append("portal_base must load rmc-friction.js")
    if not (ROOT / "scripts/report_friction_top_views.py").is_file():
        failures.append("report_friction_top_views.py missing")

    smart_links = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_smart_links_surface.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if smart_links.returncode != 0:
        failures.append(f"verify_smart_links_surface failed: {smart_links.stderr or smart_links.stdout}")

    matrix = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_customer_experience_research_matrix.py"), "--write"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if matrix.returncode != 0:
        failures.append(f"audit matrix write failed: {matrix.stderr or matrix.stdout}")

    friction_report = subprocess.run(
        [sys.executable, str(ROOT / "scripts/report_friction_top_views.py"), "--write"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if friction_report.returncode != 0:
        failures.append(
            f"report_friction_top_views failed: {friction_report.stderr or friction_report.stdout}"
        )

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1

    print("CUSTOMER_EXPERIENCE_EASE_LAYER_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
