#!/usr/bin/env python3
"""Verify role-home visual sweep harness wiring (batch 1704 / 1701 closeout)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    sweep = ROOT / "scripts/run_role_home_visual_sweep.mjs"
    orchestrator = ROOT / "scripts/run_role_home_e2e.mjs"
    workflow = ROOT / ".github/workflows/role-home-visual-sweep-e2e.yml"
    login = ROOT / "tests/e2e/helpers/tenant-login.js"
    pkg = ROOT / "package.json"

    if not orchestrator.is_file():
        errors.append("missing run_role_home_e2e.mjs")
    if not workflow.is_file():
        errors.append("missing role-home-visual-sweep-e2e.yml workflow")
    elif "role-home-marketing" not in workflow.read_text(encoding="utf-8"):
        errors.append("role-home workflow missing marketing sweep job (batch 1713)")

    if not sweep.is_file():
        errors.append("missing run_role_home_visual_sweep.mjs")
    else:
        text = sweep.read_text(encoding="utf-8")
        for needle in (
            "tenant-login.js",
            "loginTenant",
            "VISUAL_QA_PORT",
            "TENANT_SLUG",
            "runmycampus.com",
            "marketing-home",
            "marketing-threshold",
            "admin-performance",
            "ROLE_SWEEP_TENANT_ONLY",
            "host-resolver-rules",
            "VISUAL_QA_PYTHON",
        ):
            if needle not in text:
                errors.append(f"sweep script missing {needle}")

    if pkg.is_file() and "sweep:role-home:tenant" not in pkg.read_text(encoding="utf-8"):
        errors.append("package.json missing sweep:role-home:tenant script")
    if pkg.is_file() and "sweep:role-home:e2e" not in pkg.read_text(encoding="utf-8"):
        errors.append("package.json missing sweep:role-home:e2e script")

    if not login.is_file():
        errors.append("missing tenant-login.js")
    elif "requestSubmit" not in login.read_text(encoding="utf-8"):
        errors.append("tenant-login.js missing overlay-safe requestSubmit login")
    if orchestrator.is_file() and "stableOk" not in orchestrator.read_text(encoding="utf-8"):
        errors.append("run_role_home_e2e.mjs missing stable HTTP 200 server wait")
    if orchestrator.is_file() and "unlinkSync" not in orchestrator.read_text(encoding="utf-8"):
        errors.append("run_role_home_e2e.mjs missing stale sqlite cleanup before migrate")
    if orchestrator.is_file() and "process.pid" not in orchestrator.read_text(encoding="utf-8"):
        errors.append("run_role_home_e2e.mjs missing pid-scoped playwright sqlite path")
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
