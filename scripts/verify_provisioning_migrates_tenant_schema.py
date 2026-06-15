#!/usr/bin/env python3
"""Seal: the live provisioning path MUST migrate the tenant schema before seeding.

Regression guard for the 2026-06-14 production incident where
``_do_provision_tracked`` seeded a tenant schema that was never migrated to HEAD,
so ``academics_academicyear.school_id`` did not exist and the seed_data step (and
the owner's onboarding/done page + dashboard) 500'd.

The fix runs ``_run_tenant_migrations`` in the tenant_schema step, BEFORE Phase A
activation and the seed block (``_optional_tenant_context``). This AST gate fails
CI if a future edit removes that call or moves it AFTER the seed — either of which
silently reopens the leak.

stdlib-only; exit 0 clean, exit 1 on violation.
"""
from __future__ import annotations

import ast
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
TARGET = REPO / "apps" / "schools" / "tasks.py"
FUNC = "_do_provision_tracked"
MIGRATE_CALL = "_run_tenant_migrations"
SEED_CONTEXT = "_optional_tenant_context"


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return ""


def check_source(source: str) -> tuple[int, str]:
    """Return (exit_code, message) for a tasks.py source string. Testable core."""
    tree = ast.parse(source)
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == FUNC
        ),
        None,
    )
    if fn is None:
        return 1, f"FAIL: function {FUNC}() not found"

    migrate_lines = []
    seed_lines = []
    for node in ast.walk(fn):
        name = _call_name(node)
        if name == MIGRATE_CALL:
            migrate_lines.append(node.lineno)
        elif name == SEED_CONTEXT:
            seed_lines.append(node.lineno)

    if not migrate_lines:
        return 1, (
            f"FAIL: {FUNC}() never calls {MIGRATE_CALL}() — the tenant schema is "
            "not migrated before seeding. This reopens the missing-column 500 "
            "(academics school_id). Restore the migrate step in the tenant_schema "
            "phase."
        )

    if seed_lines and min(migrate_lines) > min(seed_lines):
        return 1, (
            f"FAIL: {MIGRATE_CALL}() (line {min(migrate_lines)}) runs AFTER the "
            f"seed block {SEED_CONTEXT}() (line {min(seed_lines)}). The schema "
            "must be migrated BEFORE any tenant-scoped seed/query."
        )

    return 0, (
        f"OK: {FUNC}() migrates the tenant schema "
        f"(line {min(migrate_lines)}) before seeding"
        + (f" (line {min(seed_lines)})" if seed_lines else "")
        + "."
    )


def main() -> int:
    if not TARGET.exists():
        print(f"FAIL: {TARGET} not found")
        return 1
    code, message = check_source(TARGET.read_text(encoding="utf-8"))
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
