#!/usr/bin/env python3
"""SFDP Phase 3 completion gate (batches 1452–1475)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_MODULES = (
    "apps/finance/payment_local_global_contract.py",
    "apps/finance/payment_rail_taxonomy.py",
    "apps/finance/payment_risk_tier.py",
    "apps/finance/payment_evidence_generator.py",
    "apps/finance/local_checkout_context.py",
    "apps/finance/payment_fee_labels.py",
    "apps/finance/payment_fx_display.py",
    "apps/finance/payment_dispute_local_copy.py",
    "apps/finance/views_global_payment_command_center.py",
    "apps/finance/management/commands/seed_sfdp_regional_demo_packs.py",
    "templates/finance/partials/local_checkout_rail_cards.html",
    "templates/finance/global_payment_command_center.html",
    "scripts/enrich_regional_payment_profiles_phase3.py",
    "tests/e2e/sovereign-financial-local-global.spec.js",
)


def main() -> int:
    findings: list[str] = []
    for rel in REQUIRED_MODULES:
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    checks = (
        ("verify_sovereign_financial_local_global_force.py", "SOVEREIGN_FINANCIAL_LOCAL_GLOBAL_FORCE_PASS"),
        ("verify_sovereign_financial_phase2_completion.py", "SOVEREIGN_FINANCIAL_PHASE2_COMPLETE"),
    )
    for script, token in checks:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or token not in out:
            findings.append(f"{script} failed (expected {token})")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_sqlite_memory_tests.py"),
            "apps.finance.tests.test_regional_payment_profiles_local_global_contract",
            "--verbosity=1",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        findings.append("test_regional_payment_profiles_local_global_contract failed")

    plan = (ROOT / "docs/plans/SOVEREIGN_FINANCIAL_DELIVERY_PLATFORM_PLAN.md").read_text(
        encoding="utf-8", errors="replace"
    )
    for batch in range(1452, 1476):
        if f"**{batch}**" not in plan:
            findings.append(f"plan missing batch {batch}")

    if findings:
        print("verify_sovereign_financial_local_global_completion: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(
        "verify_sovereign_financial_local_global_completion: "
        "SOVEREIGN_FINANCIAL_LOCAL_GLOBAL_FORCE_COMPLETE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
