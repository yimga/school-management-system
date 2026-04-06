#!/usr/bin/env python3
"""
§0.4 migration safety — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links staging-first migrate, Phase B execution verify, resolver ordering, and
control-plane migration surfaces. Does not run migrations.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify NORTH_STAR migration safety doc anchors (§0.4)."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_migration_safety_doc_discipline: {exc}", file=sys.stderr)
        return 1

    north_star = root / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"
    errors: list[str] = []
    if not north_star.is_file():
        errors.append(f"Missing {north_star.relative_to(root)}")
        return _fail(errors)

    text = north_star.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{north_star.relative_to(root)} missing required migration-safety anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_migration_safety_doc_discipline: PASS "
        f"({north_star.relative_to(root)} migration safety contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_migration_safety_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
