#!/usr/bin/env python3
"""CEZGP batch 1516 — Tenant launch SLA contract gate (Lane 1 static).

DB smoke lives in ``apps.customersuccess.tests`` when migrations are applied.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ok(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    checks = [
        ("csv_step", _ok("apps/customersuccess/services.py", '"student_csv_import"')),
        ("invite_step", _ok("apps/customersuccess/services.py", '"guardian_invite"')),
        ("fees_step", _ok("apps/customersuccess/services.py", '"post_fees"')),
        ("billing_step", _ok("apps/customersuccess/services.py", '"billing_estimate"')),
        ("gdpr_export_step", _ok("apps/customersuccess/services.py", "tenant_gdpr_data_export")),
        ("csv_import_verifier", (ROOT / "scripts/verify_tenant_onboarding_csv_import.py").is_file()),
        ("dry_run", _ok("apps/customersuccess/views_tenant.py", "guided_onboarding_csv_dry_run")),
        ("apply", _ok("apps/customersuccess/views_tenant.py", "guided_onboarding_csv_apply")),
        ("studio_embed", _ok("apps/setup_studio/services.py", "student-csv-import")),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        for name in failed:
            print(f"FAIL: {name}", file=sys.stderr)
        return 1
    print("TENANT_LAUNCH_SLA_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
