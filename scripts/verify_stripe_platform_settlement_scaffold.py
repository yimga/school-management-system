#!/usr/bin/env python3
"""Stripe Connect platform settlement scaffold — GEOS step 5 repo gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    required = (
        "docs/plans/STRIPE_CONNECT_PLATFORM_SETTLEMENT_PLAN.md",
        "apps/schools/stripe_connect_settings.py",
        "apps/billing/stripe_connect_onboarding.py",
        "apps/siteconfig/views_billing_stripe_connect.py",
        "templates/siteconfig/billing_stripe_connect.html",
        "var/evidence/geos-99/psp/stripe/README.md",
    )
    for rel in required:
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    urls = (ROOT / "apps/siteconfig/urls.py").read_text(encoding="utf-8", errors="replace")
    for needle in (
        'billing-stripe/"',
        "billing_stripe_connect",
        "billing_stripe_connect_start",
        "billing_stripe_connect_return",
    ):
        if needle not in urls:
            findings.append(f"siteconfig urls missing {needle!r}")

    proc = (ROOT / "apps/billing/processors.py").read_text(encoding="utf-8", errors="replace")
    if 'event_type == "account.updated"' not in proc:
        findings.append("StripeConnectProcessor missing account.updated handler")

    guide = (ROOT / "docs/payments/PSP_API_CONNECTION_GUIDE.md").read_text(
        encoding="utf-8", errors="replace"
    )
    if "Stripe Connect" not in guide or "billing-stripe" not in guide:
        findings.append("PSP guide missing Stripe Connect section")

    register = (ROOT / "docs/external_dependencies_register.json").read_text(
        encoding="utf-8", errors="replace"
    )
    if "stripe_connect_platform" not in register:
        findings.append("external_dependencies_register missing stripe_connect_platform")

    if findings:
        print("verify_stripe_platform_settlement_scaffold: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_stripe_platform_settlement_scaffold: STRIPE_PLATFORM_SETTLEMENT_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
