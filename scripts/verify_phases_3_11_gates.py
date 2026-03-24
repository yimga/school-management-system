#!/usr/bin/env python3
"""
Verify repo gates aligned with execution plan Phases 3–11 (control plane → Gilead/docs).

Runs linters and static audits that do not require a migrated test DB.
Use after code changes; DB-backed tests: see TEST_DATABASE.md and pre_deploy_gate.sh.

Exit 0 if all steps pass; non-zero on first failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(cmd: list[str], label: str) -> None:
    print(f"--- {label} ---", flush=True)
    r = subprocess.run(
        cmd,
        cwd=REPO,
        shell=False,
    )
    if r.returncode != 0:
        print(f"FAILED: {label}", file=sys.stderr)
        sys.exit(r.returncode)
    print(f"OK: {label}\n", flush=True)


def main() -> None:
    py = sys.executable
    run([py, "scripts/lint_tenant_settings.py", "--check-get-solo-only"], "Phase 5: lint_tenant_settings")
    run([py, "scripts/lint_gilead_residue.py"], "Phase 11: lint_gilead_residue")
    run([py, "scripts/lint_secret_exposure.py"], "Phase 8: lint_secret_exposure")
    run([py, "scripts/verify_sot_pillar_evidence.py"], "SOT pillar evidence (cross-phase)")
    run([py, "scripts/verify_45_wedge_scorecard.py"], "Wedge scorecard: 45 rows (Phase 2 tracker)")
    run(
        [py, "scripts/validate_wedges_phase.py", "--phase", "all"],
        "Wedges 1–45: phased execution gate (5×10)",
    )
    run([py, "scripts/verify_wedge_line_registry.py"], "Wedge line registry: 45 rows + URL reverses + beachhead slugs")
    run(
        [
            py,
            "-m",
            "pytest",
            "apps/marketplace/tests/test_marketplace_wedge_coverage.py",
            "-q",
        ],
        "Marketplace first-party: wedge_ids cover 1–45",
    )
    run([py, "scripts/verify_beachhead_checklists.py"], "Operator checklists: wedges 1–45")
    run([py, "scripts/phase_h_audit.py"], "Phase 8: phase_h_audit (static)")
    print("verify_phases_3_11_gates: all non-DB gates passed.")


if __name__ == "__main__":
    main()
