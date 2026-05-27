#!/usr/bin/env python3
"""Batch 1533 — tenant workspace canvas + column budget gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    failures: list[str] = []

    for script, extra in (
        ("verify_glocal_adoption_tranche.py", []),
        ("scan_table_column_budget.py", []),
        ("audit_isomorphic_grid_channel_sweep.py", []),
        ("verify_teacher_dashboard_rtl_playwright.py", []),
    ):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *extra],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            failures.append(script)

    if failures:
        print("verify_isomorphic_workspace_viewport: FAIL", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_isomorphic_workspace_viewport: ISOMORPHIC_WORKSPACE_VIEWPORT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
