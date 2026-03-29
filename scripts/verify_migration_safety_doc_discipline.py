#!/usr/bin/env python3
"""
§0.4 migration safety — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links staging-first migrate, Phase B execution verify, resolver ordering, and
control-plane migration surfaces. Does not run migrations.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORTH_STAR = ROOT / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"

_REQUIRED = (
    "Migration safety (operator contract",
    "RESOLVER_MIGRATE_DELETE_ORDERING.md",
    "SITECONFIG_OWNERSHIP_MIGRATION.md",
    "verify_phase_b_execution.py",
    "super:migration_cloud",
    "super:migration_rollback",
    "MIGRATION_SHADOW_RUNBOOK.md",
    "RELEASE_CHECKLIST.md",
    "verify_migration_safety_doc_discipline.py",
)


def main() -> int:
    errors: list[str] = []
    if not NORTH_STAR.is_file():
        errors.append(f"Missing {NORTH_STAR.relative_to(ROOT)}")
        return _fail(errors)

    text = NORTH_STAR.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{NORTH_STAR.relative_to(ROOT)} missing required migration-safety anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_migration_safety_doc_discipline: PASS "
        f"({NORTH_STAR.relative_to(ROOT)} migration safety contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_migration_safety_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
