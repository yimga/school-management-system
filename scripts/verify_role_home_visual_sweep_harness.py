#!/usr/bin/env python3
"""Verify role-home visual sweep harness wiring (batch 1704 / 1701 closeout)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    sweep = ROOT / "scripts/run_role_home_visual_sweep.mjs"
    login = ROOT / "tests/e2e/helpers/tenant-login.js"
    pkg = ROOT / "package.json"

    if not sweep.is_file():
        errors.append("missing run_role_home_visual_sweep.mjs")
    else:
        text = sweep.read_text(encoding="utf-8")
        for needle in (
            "tenant-login.js",
            "loginTenant",
            "VISUAL_QA_PORT",
            "127.0.0.1",
            "marketing-home",
            "marketing-threshold",
        ):
            if needle not in text:
                errors.append(f"sweep script missing {needle}")

    if not login.is_file():
        errors.append("missing tenant-login.js")
    if pkg.is_file() and "sweep:role-home" not in pkg.read_text(encoding="utf-8"):
        errors.append("package.json missing sweep:role-home script")

    if errors:
        for err in errors:
            print(f"ROLE_HOME_VISUAL_SWEEP_HARNESS_FAIL: {err}")
        return 1

    print("ROLE_HOME_VISUAL_SWEEP_HARNESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
