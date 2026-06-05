#!/usr/bin/env python3
"""CEZGP batch 1517 — parent mobile-first surface checks (plan phase 3)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PARENT_CORE = (
    "templates/parent/finance.html",
    "templates/parent/finance_pay_all_confirm.html",
    "templates/parent/settings_security.html",
    "templates/parent/contact_school.html",
    "templates/parent/dashboard.html",
)

WORKFLOW_REQUIRED = (
    "templates/parent/finance.html",
    "templates/parent/contact_school.html",
)


def _read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    failures: list[str] = []

    portal = _read("templates/portal_base.html")
    if 'name="viewport"' not in portal or "width=device-width" not in portal:
        failures.append("portal_base.html missing mobile viewport meta")

    for rel in PARENT_CORE:
        if not (ROOT / rel).is_file():
            failures.append(f"missing {rel}")
            continue
        body = _read(rel)
        if "btn " not in body and "rmc-btn" not in body:
            failures.append(f"{rel} missing actionable controls")
        if rel in WORKFLOW_REQUIRED and "rmc_tools_tray_context_stack.html" not in _read(
            "templates/partials/rmc_tenant_tools_scripts.html"
        ):
            failures.append(f"{rel}: tenant tools tray must ship workflow context stack")

    finance = _read("templates/parent/finance.html")
    if finance and "parent_finance_pay_all" not in finance and "pay-all" not in finance.lower():
        if "parent_finance_pay_all" not in finance:
            failures.append("parent/finance.html missing pay-all CTA wiring")

    security = _read("templates/parent/settings_security.html")
    if security and "passkey" not in security.lower():
        failures.append("settings_security.html missing passkey CTA")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1

    print("PARENT_MOBILE_FIRST_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
