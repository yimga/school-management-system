#!/usr/bin/env python3
"""Batch 1728 bundle — tenant surface exception program (Waves A–D1 repo scope)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

VERIFIERS = [
    "scripts/scan_operator_shell_dead_hrefs.py",
    "scripts/verify_interaction_integrity_completion.py",
    "scripts/verify_tenant_sidebar_baseline_integrity.py",
    "scripts/verify_tenant_menu_p0_sweep_harness.py",
    "scripts/verify_tenant_exception_task_surfaces.py",
    "scripts/verify_tenant_copilot_expand_contract.py",
    "scripts/verify_copilot_chrome_stack.py",
    "scripts/verify_operator_tools_tray.py",
    "scripts/verify_tenant_preview_to_live_adoption.py",
    "scripts/verify_role_home_visual_sweep_harness.py",
]


def main() -> int:
    failures: list[str] = []
    for script in VERIFIERS:
        path = ROOT / script
        extra: list[str] = []
        if script.endswith("scan_operator_shell_dead_hrefs.py"):
            extra = ["--strict"]
        proc = subprocess.run(
            [PY, str(path), *extra],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            failures.append(f"{script} exit {proc.returncode}")
            for line in out.strip().splitlines()[-4:]:
                failures.append(f"  {line}")
    if failures:
        print("verify_tenant_surface_exception_program: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1
    print("verify_tenant_surface_exception_program: TENANT_SURFACE_EXCEPTION_PROGRAM_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
