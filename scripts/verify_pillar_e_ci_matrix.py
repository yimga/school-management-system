#!/usr/bin/env python3
"""Verify Pillar E CI matrix artifacts (batches 1732–1742)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NPM_SCRIPTS = (
    "test:e2e:tenant-readiness-offline",
    "test:e2e:tenant-journey-pillar-e:armed",
)


def main() -> int:
    errors: list[str] = []

    matrix = ROOT / "docs/phase_checklists/PILLAR_E_OFFLINE_CI_MATRIX.md"
    if not matrix.is_file():
        errors.append("missing PILLAR_E_OFFLINE_CI_MATRIX.md")

    pkg_path = ROOT / "package.json"
    if not pkg_path.is_file():
        errors.append("missing package.json")
    else:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        scripts = (pkg.get("scripts") or {})
        for name in NPM_SCRIPTS:
            if name not in scripts:
                errors.append(f"package.json missing npm script {name}")

    setup = (ROOT / "templates/partials/tenant/setup_command_surface.html").read_text(
        encoding="utf-8"
    )
    for needle in (
        "provisioning_partial_failure_banner",
        "rmc-journey-offline-mirror.js",
    ):
        if needle not in setup:
            errors.append(f"setup_command_surface missing {needle}")

    verifiers = (
        "verify_tenant_lifecycle_world_class_program.py",
        "verify_provisioning_golive_program.py",
        "verify_offline_workflow_apply.py",
    )
    for script in verifiers:
        path = ROOT / "scripts" / script
        if not path.is_file():
            errors.append(f"missing {script}")
            continue
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            errors.append(f"{script} failed: {(proc.stdout or proc.stderr).strip()[:200]}")

    if errors:
        print("verify_pillar_e_ci_matrix: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("verify_pillar_e_ci_matrix: PILLAR_E_CI_MATRIX_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
