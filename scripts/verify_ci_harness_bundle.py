#!/usr/bin/env python3
"""Verify Playwright + 50-app matrix CI harness wiring (batch 1716)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HARNESS_SCRIPTS = (
    "scripts/verify_role_home_visual_sweep_harness.py",
    "scripts/verify_globe_layout_playwright_ci_harness.py",
    "scripts/verify_50_app_test_matrix_ci_harness.py",
)


def main() -> int:
    errors: list[str] = []
    for rel in HARNESS_SCRIPTS:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing {rel}")
            continue
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stdout or proc.stderr or "").strip().splitlines()
            tail = detail[-1] if detail else f"exit {proc.returncode}"
            errors.append(f"{rel}: {tail}")

    workflow = ROOT / ".github/workflows/architectural-boundaries.yml"
    if workflow.is_file():
        wf = workflow.read_text(encoding="utf-8")
        if "playwright-ci-harness:" not in wf:
            errors.append("architectural-boundaries.yml missing playwright-ci-harness job")
        if "verify_ci_harness_bundle.py" not in wf:
            errors.append("architectural-boundaries.yml missing verify_ci_harness_bundle.py step")
    else:
        errors.append("missing architectural-boundaries.yml")

    if errors:
        for err in errors:
            print(f"CI_HARNESS_BUNDLE_FAIL: {err}")
        return 1

    print("CI_HARNESS_BUNDLE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
