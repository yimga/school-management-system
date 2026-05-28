#!/usr/bin/env python3
"""CEZGP Lane 2 — close six partial matrix rows (1523)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []

    checks = [
        ("P2 password_reset", _contains("apps/accounts/urls.py", 'name="password_reset"')),
        ("P2 login CTA", _contains("templates/auth/login.html", "data-rmc-parent-password-reset")),
        ("P2 guardian chrome", _contains("templates/portal_base.html", "guardian_student_links.html")),
        ("P7c migration module", _exists("apps/feedback/legacy_product_feedback_migration.py")),
        ("P7c migration command", _exists("apps/feedback/management/commands/migrate_product_feedback_legacy.py")),
        ("P8b gdpr view", _exists("apps/lifecycle/views_tenant_gdpr_export.py")),
        ("P8b gdpr url", _contains("config/tenant_urls.py", "tenant_gdpr_data_export")),
        ("P10 pricing crosswalk", _contains("apps/customersuccess/pricing_billing_clarity.py", "pricing_clarity_crosswalk")),
        ("B6 billing estimate url", _contains("apps/siteconfig/urls.py", "tenant_billing_estimate")),
        ("PILLAR_AMAZON frame", _contains("templates/marketplace/governance_console.html", "marketplace-operator-frame")),
    ]
    for label, ok in checks:
        if not ok:
            failures.append(label)

    proc = subprocess.run(
        [sys.executable, "scripts/audit_customer_experience_research_matrix.py", "--strict-zero-partials", "--write"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        failures.append("matrix --strict-zero-partials")

    if failures:
        print("verify_customer_experience_lane2_partial_closeout: FAIL", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr[-600:], file=sys.stderr)
        return 1

    print("CUSTOMER_EXPERIENCE_LANE2_PARTIAL_CLOSEOUT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
