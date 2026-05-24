#!/usr/bin/env python3
"""SFDP Phase 2 scaffold gate (batches 1432–1448 Lane 1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PHASE2_ARTIFACTS = (
    "apps/finance/payment_lane2_checklist.py",
    "apps/finance/payment_lane2_status.py",
    "apps/finance/payment_corridor_contracts.py",
    "scripts/verify_payment_gateway_lane2_scaffold.py",
    "scripts/verify_dual_engine_financial_program.py",
    "scripts/generate_regional_payment_catalog_stubs.py",
)


def main() -> int:
    findings: list[str] = []
    for rel in PHASE2_ARTIFACTS:
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    plan = (ROOT / "docs/plans/SOVEREIGN_FINANCIAL_DELIVERY_PLATFORM_PLAN.md").read_text(
        encoding="utf-8", errors="replace"
    )
    if "## 8 — Phase 2" not in plan:
        findings.append("SFDP plan missing §8 Phase 2")

    sot = (ROOT / "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md").read_text(
        encoding="utf-8", errors="replace"
    )
    for batch in range(1432, 1449):
        if f"batch {batch}" not in sot.lower():
            findings.append(f"SOT missing batch {batch}")

    lane2 = ROOT / "scripts/verify_payment_gateway_lane2_scaffold.py"
    if lane2.is_file():
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(lane2)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0 or "PAYMENT_GATEWAY_LANE2_SCAFFOLD_PASS" not in (
            (proc.stdout or "") + (proc.stderr or "")
        ):
            findings.append("verify_payment_gateway_lane2_scaffold failed")
    else:
        findings.append("missing verify_payment_gateway_lane2_scaffold.py")

    if findings:
        print("verify_sovereign_financial_phase2_scaffold: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_sovereign_financial_phase2_scaffold: SOVEREIGN_FINANCIAL_PHASE2_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
