#!/usr/bin/env python3
"""Verify 50-app Django test matrix CI harness (batch 1714)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    runner = ROOT / "scripts/run_50_app_test_shards.py"
    workflow = ROOT / ".github/workflows/django-50-app-matrix.yml"

    if not runner.is_file():
        errors.append("missing run_50_app_test_shards.py")
    else:
        text = runner.read_text(encoding="utf-8")
        if "FIFTY_APP_TEST_MATRIX_PASS" not in text:
            errors.append("run_50_app_test_shards.py missing FIFTY_APP_TEST_MATRIX_PASS token")
        if "--isolation app" not in text:
            errors.append("run_50_app_test_shards.py missing --isolation app mode")

    if not workflow.is_file():
        errors.append("missing django-50-app-matrix.yml workflow")
    else:
        wf = workflow.read_text(encoding="utf-8")
        for needle in (
            "run_50_app_test_shards.py",
            "--isolation app",
            "FIFTY_APP_TEST_MATRIX_PASS",
            "RMC_SQLITE_TEST_MEMORY",
        ):
            if needle not in wf:
                errors.append(f"50-app workflow missing {needle}")

    if errors:
        for err in errors:
            print(f"FIFTY_APP_TEST_MATRIX_CI_HARNESS_FAIL: {err}")
        return 1

    print("FIFTY_APP_TEST_MATRIX_CI_HARNESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
