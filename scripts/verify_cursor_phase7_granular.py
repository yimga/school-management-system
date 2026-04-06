#!/usr/bin/env python3
"""
Cursor Phase 7 — Runtime-first — granular gate (execution law).

Runs the Phase 7 mechanical checks (with pytest deferred from the narrow script),
all tenant-setting lints (including Studio OS), then one pytest session covering
Phase 7 contract tests plus tenant identity and truth-hub contract tests. The
combined pytest avoids back-to-back SQLite locks on Windows. Use after code changes;
do not treat Phase 7 as “documentation complete” without this script passing.

Exit 0 = all checks pass.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Cursor Phase 7 granular runtime-first checks."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _run(
    cmd: list[str],
    label: str,
    *,
    root: Path,
    env: dict[str, str] | None = None,
) -> str | None:
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=360,
        env=env,
    )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print("verify_cursor_phase7_granular: FAIL", file=sys.stderr)
        print(f"  ---\n{exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    py = sys.executable
    phase7 = root / "scripts" / "verify_cursor_phase7_runtime_first.py"
    audit = root / "docs" / "phase_audit" / "PHASE_07_RUNTIME_FIRST_AUDIT.md"

    if not audit.is_file():
        errors.append(f"Missing {audit.relative_to(root)}")

    if not phase7.is_file():
        errors.append(f"Missing {phase7.relative_to(root)}")
    else:
        env = os.environ.copy()
        env["PHASE7_RUNTIME_FIRST_SKIP_PYTEST"] = "1"
        if err := _run(
            [py, str(phase7)],
            "verify_cursor_phase7_runtime_first",
            root=root,
            env=env,
        ):
            errors.append(err)

    if err := _run(
        [py, str(root / "scripts" / "lint_sitesettings_orm_singleton.py"), "--base", str(root)],
        "lint_sitesettings_orm_singleton",
        root=root,
    ):
        errors.append(err)

    for args, label in (
        (
            [
                py,
                str(root / "scripts" / "lint_tenant_settings.py"),
                "--check-get-solo-only",
                "--base",
                str(root),
            ],
            "lint_tenant_settings --check-get-solo-only",
        ),
        (
            [
                py,
                str(root / "scripts" / "lint_tenant_settings.py"),
                "--check-school-settings-features",
                "--base",
                str(root),
            ],
            "lint_tenant_settings --check-school-settings-features",
        ),
        (
            [
                py,
                str(root / "scripts" / "lint_tenant_settings.py"),
                "--check-sitesettings-orm-in-tenant-apps",
                "--base",
                str(root),
            ],
            "lint_tenant_settings --check-sitesettings-orm-in-tenant-apps",
        ),
    ):
        if err := _run(args, label, root=root):
            errors.append(err)

    # Single pytest session: Phase 7 contract modules + tenant/middleware + truth hub (avoids SQLite lock flakiness).
    if err := _run(
        [
            py,
            "-m",
            "pytest",
            "apps/platform_runtime/tests/test_phase7_runtime_gate.py",
            "apps/platform_runtime/tests/test_precedence.py",
            "apps/platform_runtime/tests/test_runtime_contract.py",
            "apps/platform_runtime/tests/test_tenant_isolation_and_identity.py",
            "apps/schools/tests/test_super_views_runtime_ops.py",
            "-q",
            "--no-header",
        ],
        "pytest Phase 7 contract + tenant identity + super runtime ops (truth hub)",
        root=root,
    ):
        errors.append(err)

    if errors:
        print("verify_cursor_phase7_granular: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  ---\n{e}", file=sys.stderr)
        return 1

    print(
        "verify_cursor_phase7_granular: PASS",
        "(singleton ORM lint + Phase 7 checks + 3 tenant lints + one pytest: Phase7 contract + identity + truth hub)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
