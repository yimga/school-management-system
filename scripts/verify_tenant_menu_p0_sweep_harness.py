#!/usr/bin/env python3
"""Batch 1728 Wave D1 — P0 menu sweep surfaces ledger + harness wiring."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
LEDGER = ROOT / "docs" / "generated" / "tenant_p0_menu_sweep_surfaces.json"
GENERATOR = ROOT / "scripts" / "generate_tenant_p0_menu_sweep_surfaces.py"
SWEEP = ROOT / "scripts" / "run_role_home_visual_sweep.mjs"


def main() -> int:
    failures: list[str] = []

    if not GENERATOR.is_file():
        failures.append("missing generate_tenant_p0_menu_sweep_surfaces.py")
    else:
        proc = subprocess.run(
            [PY, str(GENERATOR), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            failures.append("tenant_p0_menu_sweep_surfaces.json drift — run generator --write")
            for line in (proc.stdout or proc.stderr or "").strip().splitlines()[-3:]:
                failures.append(f"  {line}")

    if not LEDGER.is_file():
        failures.append(f"missing {LEDGER.relative_to(ROOT)}")
    else:
        try:
            payload = json.loads(LEDGER.read_text(encoding="utf-8"))
            count = int(payload.get("surface_count") or 0)
            surfaces = payload.get("surfaces") or []
            if count < 10 or len(surfaces) != count:
                failures.append(f"expected >=10 P0 surfaces, got count={count} len={len(surfaces)}")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            failures.append(f"invalid ledger JSON: {exc}")

    if SWEEP.is_file():
        text = SWEEP.read_text(encoding="utf-8")
        for needle in ("ROLE_SWEEP_P0_MENUS", "tenant-menu-p0-sweep.json", "loadP0MenuSurfaces"):
            if needle not in text:
                failures.append(f"sweep script missing {needle}")
    else:
        failures.append("missing run_role_home_visual_sweep.mjs")

    workflow = ROOT / ".github/workflows/role-home-visual-sweep-e2e.yml"
    if not workflow.is_file():
        failures.append("missing role-home-visual-sweep-e2e.yml")
    elif "role-home-p0-menus" not in workflow.read_text(encoding="utf-8"):
        failures.append("CI workflow missing role-home-p0-menus job")

    sidebar = subprocess.run(
        [PY, str(ROOT / "scripts" / "verify_tenant_sidebar_baseline_integrity.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if sidebar.returncode != 0:
        failures.append("verify_tenant_sidebar_baseline_integrity failed")

    if failures:
        print("verify_tenant_menu_p0_sweep_harness: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1

    print("verify_tenant_menu_p0_sweep_harness: TENANT_MENU_P0_SWEEP_HARNESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
