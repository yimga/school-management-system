#!/usr/bin/env python3
"""CEZGP batch 1521 — parent global-local slice gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    view = ROOT / "apps/portal/views_parent_finance.py"
    dashboard = ROOT / "templates/parent/dashboard.html"
    pwa_js = ROOT / "static/js/rmc-pwa-install-cta.js"
    notify = ROOT / "apps/finance/payment_notification_intent.py"
    resolvers = ROOT / "apps/policies/resolvers.py"

    for path in (view, dashboard, pwa_js, notify, resolvers):
        if not path.is_file():
            findings.append(f"missing {path.relative_to(ROOT)}")

    if view.is_file() and "regional_payment" not in view.read_text(encoding="utf-8"):
        findings.append("pay-all view missing regional_payment_profiles")

    if dashboard.is_file():
        dash = dashboard.read_text(encoding="utf-8")
        if "data-rmc-pwa-install-cta" not in dash:
            findings.append("dashboard missing PWA install CTA")
        if "show_pwa_install_cta" not in dash:
            findings.append("dashboard missing show_pwa_install_cta flag gate")

    if notify.is_file() and "quiet_hours" not in notify.read_text(encoding="utf-8"):
        findings.append("payment_notification_intent missing quiet_hours hook")

    if resolvers.is_file() and "is_within_quiet_hours" not in resolvers.read_text(encoding="utf-8"):
        findings.append("policies/resolvers missing is_within_quiet_hours")

    if findings:
        print("verify_customer_experience_global_local: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_customer_experience_global_local: CUSTOMER_EXPERIENCE_GLOBAL_LOCAL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
