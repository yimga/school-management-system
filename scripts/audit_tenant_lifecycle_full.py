#!/usr/bin/env python3
"""
Run full tenant lifecycle audit: scroll, workflows, offboarding, signup wiring.

Exits non-zero on any failure. Intended for CI and pre-deploy operator checks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = (
    "scripts/audit_shell_scroll_contract.py",
    "scripts/audit_tenant_lifecycle_workflows.py",
    "scripts/verify_tenant_lifecycle_unified.py",
    "scripts/verify_tenant_offboarding_surface.py",
    "scripts/verify_platform_back_to_top.py",
)

SIGNUP_WIRING = (
    ("apps/schools/signup_views.py", "send_transactional"),
    ("apps/schools/signup_views.py", "SignupVerification"),
    ("apps/schools/signup_views.py", "verify-signup"),
    ("apps/schools/tenant_offboarding.py", "request_self_service_closure"),
    ("apps/schools/tenant_offboarding.py", "force_operator"),
    ("templates/schools/super_offboarding_queue.html", "data-rmc-auto-purge-disabled-banner"),
    ("templates/schools/super_offboarding_queue.html", "data-rmc-run-scheduled-apply"),
    ("static/js/_pages/schools__super_offboarding_queue-1.js", "force_operator"),
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
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def main() -> int:
    failures: list[str] = []

    for rel, needle in SIGNUP_WIRING:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing file: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"{rel}: missing `{needle}`")

    for script in SCRIPTS:
        code, out = _run(script)
        if code != 0:
            failures.append(f"{script} failed:\n{out[:500]}")

    if failures:
        print("TENANT_LIFECYCLE_FULL_AUDIT_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    code, out = _run("scripts/audit_tenant_lifecycle_aggressive.py")
    if code != 0:
        print("TENANT_LIFECYCLE_FULL_AUDIT_FAIL")
        print(out[:800])
        return 1

    print("TENANT_LIFECYCLE_FULL_AUDIT_PASS")
    print(f"  verifiers: {len(SCRIPTS)}  wiring checks: {len(SIGNUP_WIRING)}")
    print("  aggressive: TENANT_LIFECYCLE_AGGRESSIVE_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
