#!/usr/bin/env python3
"""Tenant lifecycle 10x gate — unified wiring + workflow hub + playbook surfaces."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUBPROCESS_SCRIPTS = (
    "scripts/verify_tenant_lifecycle_unified.py",
    "scripts/audit_tenant_lifecycle_workflows.py",
)

STATIC_MARKERS = (
    (
        "apps/lifecycle/views_tenant_lifecycle.py",
        "onboarding_playbook_api_url",
    ),
    (
        "templates/siteconfig/tenant_lifecycle_command_center.html",
        "workflow_playbook_assistant.html",
    ),
    (
        "templates/siteconfig/tenant_lifecycle_command_center.html",
        "section-lifecycle-playbook",
    ),
    (
        "scripts/generate_portal_tenant_sweep_routes.py",
        "/school/studio/lifecycle/",
    ),
    (
        "scripts/run_tenant_studio_abrupt_end_sweep.sh",
        "ensure_demo_environment",
    ),
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

    for script in SUBPROCESS_SCRIPTS:
        code, out = _run(script)
        if code != 0:
            failures.append(f"{script}:\n{out[:500]}")

    for rel, needle in STATIC_MARKERS:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing file: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"{rel}: missing `{needle}`")

    if failures:
        print("TENANT_LIFECYCLE_10X_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("TENANT_LIFECYCLE_10X_PASS")
    print(f"  subprocess gates: {len(SUBPROCESS_SCRIPTS)}")
    print(f"  static markers: {len(STATIC_MARKERS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
