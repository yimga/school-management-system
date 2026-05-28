#!/usr/bin/env python3
"""Orchestrate glocal §D practical closeout (repo-contained slices)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS: tuple[tuple[str, list[str]], ...] = (
    ("verify_glocal_adoption_tranche.py", []),
    ("refresh_residency_lane2_evidence.py", []),
    ("verify_teacher_dashboard_rtl_playwright.py", []),
    ("verify_glocal_out_of_scope_honesty.py", []),
)


def _run(script: str, extra: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
    return proc.returncode == 0, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-playwright",
        action="store_true",
        help="Pass --run to teacher RTL Playwright when Django is up.",
    )
    parser.add_argument(
        "--include-cezgp",
        action="store_true",
        help="Also run verify_customer_experience_zero_gap.py (slow).",
    )
    args = parser.parse_args()

    failures: list[str] = []
    for script, extra in STEPS:
        if script == "verify_teacher_dashboard_rtl_playwright.py" and args.live_playwright:
            extra = ["--run", "--spawn-server"]
        ok, tail = _run(script, extra)
        if not ok:
            failures.append(f"{script}: {tail}")

    if args.include_cezgp:
        ok, tail = _run("verify_customer_experience_zero_gap.py", [])
        if not ok:
            failures.append(f"verify_customer_experience_zero_gap.py: {tail}")

    if failures:
        print("verify_glocal_practical_closeout: FAIL", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_glocal_practical_closeout: GLOCAL_PRACTICAL_CLOSEOUT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
