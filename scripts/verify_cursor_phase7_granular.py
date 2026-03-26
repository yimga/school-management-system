#!/usr/bin/env python3
"""
Cursor Phase 7 — Runtime-first — granular gate (execution law).

Runs the Phase 7 mechanical checks (with pytest deferred from the narrow script),
all tenant-setting lints (including Studio OS), then one pytest session covering
Phase 7 contract tests plus tenant identity and truth-hub contract tests. The
combined pytest avoids back-to-back SQLite locks on Windows. Use after code changes;
do not treat Phase 7 as “documentation complete” without this script passing.

Exit 0 = all checks pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASE7 = ROOT / "scripts" / "verify_cursor_phase7_runtime_first.py"
AUDIT = ROOT / "docs" / "phase_audit" / "PHASE_07_RUNTIME_FIRST_AUDIT.md"


def _run(cmd: list[str], label: str) -> str | None:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=360,
    )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def main() -> int:
    errors: list[str] = []
    py = sys.executable

    if not AUDIT.is_file():
        errors.append(f"Missing {AUDIT.relative_to(ROOT)}")

    if not PHASE7.is_file():
        errors.append(f"Missing {PHASE7.relative_to(ROOT)}")
    else:
        env = os.environ.copy()
        env["PHASE7_RUNTIME_FIRST_SKIP_PYTEST"] = "1"
        proc = subprocess.run(
            [py, str(PHASE7)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=360,
            env=env,
        )
        if proc.returncode != 0:
            errors.append(
                "verify_cursor_phase7_runtime_first failed (exit "
                f"{proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
            )

    if err := _run(
        [py, str(ROOT / "scripts" / "lint_sitesettings_orm_singleton.py"), "--base", str(ROOT)],
        "lint_sitesettings_orm_singleton",
    ):
        errors.append(err)

    for args, label in (
        (
            [
                py,
                str(ROOT / "scripts" / "lint_tenant_settings.py"),
                "--check-get-solo-only",
                "--base",
                str(ROOT),
            ],
            "lint_tenant_settings --check-get-solo-only",
        ),
        (
            [
                py,
                str(ROOT / "scripts" / "lint_tenant_settings.py"),
                "--check-school-settings-features",
                "--base",
                str(ROOT),
            ],
            "lint_tenant_settings --check-school-settings-features",
        ),
        (
            [
                py,
                str(ROOT / "scripts" / "lint_tenant_settings.py"),
                "--check-sitesettings-orm-in-tenant-apps",
                "--base",
                str(ROOT),
            ],
            "lint_tenant_settings --check-sitesettings-orm-in-tenant-apps",
        ),
    ):
        if err := _run(args, label):
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
    raise SystemExit(main())
