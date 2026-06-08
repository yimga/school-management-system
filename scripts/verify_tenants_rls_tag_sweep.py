#!/usr/bin/env python3
"""Ensure canonical tenant-isolation test modules carry @tag('tenants_rls')."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TAGGED = [
    "apps/evals/tests/test_bulk_grade_tenant_context.py",
    "apps/finance/tests/test_signal_tenant_context.py",
    "apps/portal/tests/test_cross_module_support_isolation.py",
    "apps/schools/tests/test_tenant_isolation_rls_mode.py",
    "apps/schools/tests/test_multi_tenant_isolation.py",
    "apps/security/tests/test_tenant_breach_scenarios.py",
    "apps/security/tests/test_tenant_route_leakage.py",
    "apps/tenancy/tests/test_rls_boundary_contracts.py",
    "apps/api/tests/test_tenant_idor_guards.py",
    "apps/api/tests/test_search_api_tenant_scope.py",
    "apps/communication/tests/test_api_tenant_isolation.py",
    "apps/reports/tests/test_adhoc_tenant_scope.py",
    "apps/evals/tests/test_rankings_cache_tenant_context.py",
    "apps/automation/tests/test_domain_event_bridge.py",
    "apps/social_media/tests/test_social_isolation.py",
]


def main() -> int:
    errors: list[str] = []
    for rel in REQUIRED_TAGGED:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing file: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if '@tag("tenants_rls")' not in text and "@tag('tenants_rls')" not in text:
            errors.append(f"{rel} missing @tag('tenants_rls')")

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        print("TENANTS_RLS_TAG_SWEEP: FAIL")
        return 1

    print(f"TENANTS_RLS_TAG_SWEEP: PASS ({len(REQUIRED_TAGGED)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
