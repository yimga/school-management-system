#!/usr/bin/env python3
"""Lane-1 deferred finish gate (batch 1267): burndown 0, snapshots, scaffolds."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    baseline = ROOT / "var" / "security-audit-baseline-tenant-isolation.json"
    if baseline.is_file():
        count = json.loads(baseline.read_text(encoding="utf-8")).get("finding_count")
        if count != 0:
            errors.append(f"tenant baseline finding_count={count}, want 0")
    snap_dir = ROOT / "tests" / "e2e" / "marketing-snapshots.spec.js-snapshots"
    pngs = list(snap_dir.glob("*.png")) if snap_dir.is_dir() else []
    if len(pngs) < 3:
        errors.append(f"expected >=3 marketing snapshot PNGs, found {len(pngs)}")

    checks = [
        [sys.executable, str(ROOT / "scripts" / "verify_cache_rankings_interval_parity.py")],
        [sys.executable, str(ROOT / "scripts" / "verify_top_students_default_limit_parity.py")],
        [sys.executable, str(ROOT / "scripts" / "verify_rls_migration_0048_repo.py")],
        [sys.executable, str(ROOT / "scripts" / "verify_tenant_owned_model_adoption_scaffold.py")],
        [sys.executable, str(ROOT / "scripts" / "verify_marketing_snapshots_scaffold.py")],
        [sys.executable, str(ROOT / "scripts" / "verify_marketing_axe_ci_ready.py")],
    ]
    for cmd in checks:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        if proc.returncode != 0:
            errors.append(f"{cmd[-1]} failed:\n{proc.stdout}\n{proc.stderr}")

    k6_path = ROOT / "docs" / "generated" / "k6_baseline_last_run.json"
    if not k6_path.is_file():
        errors.append("missing docs/generated/k6_baseline_last_run.json")

    if errors:
        for e in errors:
            print(f"verify_deferred_lane1_finish: {e}", file=sys.stderr)
        return 1
    print("verify_deferred_lane1_finish: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
