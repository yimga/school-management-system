#!/usr/bin/env python3
"""Moderator program bundle — global multi-tenant + tenant customer 250 seal (batch 1726)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

VERIFIERS: list[str] = [
    "scripts/verify_operational_lifecycle_fsm_coverage.py",
    "scripts/verify_tenant_manifest_runtime_consistency.py",
    "scripts/verify_tenant_customer_250_country_matrix.py",
    "scripts/verify_tenant_seed_blueprint.py",
    "scripts/verify_new_test_high_school_customer_delivery.py",
    "scripts/verify_tenant_experience_competitor_gap_closure.py",
]


def main() -> int:
    failures: list[str] = []
    for script in VERIFIERS:
        path = ROOT / script
        if not path.is_file():
            failures.append(f"missing {script}")
            continue
        proc = subprocess.run(
            [PY, str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            failures.append(f"{script} exit {proc.returncode}")
            for line in out.strip().splitlines()[-5:]:
                failures.append(f"  {line}")
    if failures:
        print("verify_global_tenant_seal_program: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1
    print("verify_global_tenant_seal_program: GLOBAL_TENANT_SEAL_PROGRAM_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
