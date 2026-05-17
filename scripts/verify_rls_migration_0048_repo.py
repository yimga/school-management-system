#!/usr/bin/env python3
"""Repo gate: schools migration 0048 (FORCE RLS) exists and is documented."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "apps" / "schools" / "migrations" / "0048_force_rls_on_all_enabled_tables.py"
WORKFLOW = ROOT / ".github" / "workflows" / "tenants-rls.yml"


def main() -> int:
    errors: list[str] = []
    if not MIGRATION.is_file():
        errors.append("missing apps/schools/migrations/0048_force_rls_on_all_enabled_tables.py")
    else:
        body = MIGRATION.read_text(encoding="utf-8")
        if "relforcerowsecurity" not in body and "FORCE ROW LEVEL SECURITY" not in body.upper():
            errors.append("0048 migration must force RLS on enabled tables")
    if not WORKFLOW.is_file():
        errors.append("missing .github/workflows/tenants-rls.yml")
    if errors:
        for e in errors:
            print(f"verify_rls_migration_0048_repo: {e}", file=sys.stderr)
        return 1
    print("verify_rls_migration_0048_repo: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
