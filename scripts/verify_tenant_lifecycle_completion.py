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
    "scripts/verify_tenant_lifecycle_10x.py",
)

LANE2_CHECKLIST = ROOT / "docs" / "TENANT_LIFECYCLE_LANE2_OPERATOR_CHECKLIST.md"
LANE2_RENDER_ENV_SOT = ROOT / "docs" / "TENANT_OFFBOARDING.md"

LANE2_OFFBOARDING_MARKERS = (
    "Render (Lane 2)",
    "TENANT_AUTO_PURGE_ENABLED",
    "/super/email/health/",
    "/super/signup/diagnostics/",
    "async_send=True",
    "DEFAULT_FROM_EMAIL",
    "EMAIL_BACKEND",
)


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
        "build_offboarding_exit_status",
    ):
        if needle not in matrix:
            failures.append(f"enrollment_workflow_matrix missing state `{needle}`")

    if not LANE2_CHECKLIST.is_file():
        failures.append("missing docs/TENANT_LIFECYCLE_LANE2_OPERATOR_CHECKLIST.md")

    if not LANE2_RENDER_ENV_SOT.is_file():
        failures.append("missing docs/TENANT_OFFBOARDING.md (Lane 2 Render env SOT)")
    else:
        offboarding_doc = LANE2_RENDER_ENV_SOT.read_text(
            encoding="utf-8", errors="replace"
        )
        for needle in LANE2_OFFBOARDING_MARKERS:
            if needle not in offboarding_doc:
                failures.append(
                    f"TENANT_OFFBOARDING.md missing Lane 2 marker `{needle}`"
                )

    if failures:
        print("TENANT_LIFECYCLE_COMPLETION_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("TENANT_LIFECYCLE_COMPLETION_PASS")
    print("  Lane 1: full audit + unified lifecycle wiring")
    print(f"  Lane 2: checklist {LANE2_CHECKLIST.name}")
    print(f"  Lane 2: Render env SOT {LANE2_RENDER_ENV_SOT.name} (operator proof on deploy)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
