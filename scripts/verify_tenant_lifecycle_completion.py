#!/usr/bin/env python3
"""Single gate: tenant lifecycle + offboarding + scroll — repo-complete (Lane 1)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LANE1_SCRIPTS = (
    "scripts/audit_tenant_lifecycle_full.py",
    "scripts/verify_tenant_lifecycle_unified.py",
)

LANE2_EVIDENCE = ROOT / "docs" / "TENANT_LIFECYCLE_LANE2_OPERATOR_CHECKLIST.md"


def _run(script: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def main() -> int:
    failures: list[str] = []

    for script in LANE1_SCRIPTS:
        code, out = _run(script)
        if code != 0:
            failures.append(f"{script}:\n{out[:400]}")

    matrix = (ROOT / "apps/lifecycle/enrollment_workflow_matrix.py").read_text(
        encoding="utf-8", errors="replace"
    )
    for needle in (
        "guardian_invite_claimed",
        "purge_scheduled",
        "signup_verified",
        "applicant_enrolled",
    ):
        if needle not in matrix:
            failures.append(f"enrollment_workflow_matrix missing state `{needle}`")

    if not LANE2_EVIDENCE.is_file():
        failures.append("missing docs/TENANT_LIFECYCLE_LANE2_OPERATOR_CHECKLIST.md")

    if failures:
        print("TENANT_LIFECYCLE_COMPLETION_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("TENANT_LIFECYCLE_COMPLETION_PASS")
    print("  Lane 1: full audit + unified lifecycle wiring")
    print(f"  Lane 2: operator checklist at {LANE2_EVIDENCE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
