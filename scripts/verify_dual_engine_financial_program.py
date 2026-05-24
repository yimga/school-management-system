#!/usr/bin/env python3
"""Dual-engine financial program gate — Engine 1 (Stripe) + Engine 2 (SFDP Lane 1)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(script: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def main() -> int:
    findings: list[str] = []

    for rel in (
        "docs/plans/SOVEREIGN_FINANCIAL_DELIVERY_PLATFORM_PLAN.md",
        "docs/plans/STRIPE_CONNECT_PLATFORM_SETTLEMENT_PLAN.md",
        "apps/finance/payment_lane2_checklist.py",
        "apps/finance/payment_provision.py",
        "apps/schools/stripe_connect_settings.py",
        "apps/billing/stripe_connect_onboarding.py",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    checks = (
        ("verify_stripe_platform_settlement_scaffold.py", "STRIPE_PLATFORM_SETTLEMENT_SCAFFOLD_PASS"),
        ("verify_sovereign_financial_delivery_scaffold.py", "SOVEREIGN_FINANCIAL_DELIVERY_SCAFFOLD_PASS"),
        ("verify_sovereign_financial_delivery_completion.py", "SOVEREIGN_FINANCIAL_DELIVERY_COMPLETE"),
        ("verify_payment_gateway_lane2_scaffold.py", "PAYMENT_GATEWAY_LANE2_SCAFFOLD_PASS"),
        ("verify_sovereign_financial_phase2_scaffold.py", "SOVEREIGN_FINANCIAL_PHASE2_SCAFFOLD_PASS"),
        ("verify_sovereign_financial_phase2_completion.py", "SOVEREIGN_FINANCIAL_PHASE2_COMPLETE"),
        ("verify_sovereign_financial_local_global_force.py", "SOVEREIGN_FINANCIAL_LOCAL_GLOBAL_FORCE_PASS"),
        ("verify_sovereign_financial_local_global_completion.py", "SOVEREIGN_FINANCIAL_LOCAL_GLOBAL_FORCE_COMPLETE"),
    )
    import subprocess as sp

    for script, token in checks:
        proc = sp.run(
            [sys.executable, str(ROOT / "scripts" / script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or token not in out:
            findings.append(f"{script} failed (expected {token})")

    register = (ROOT / "docs/external_dependencies_register.json").read_text(
        encoding="utf-8", errors="replace"
    )
    for rid in (
        "stripe_global_cards",
        "stripe_connect_platform",
        "paystack_wa",
        "flutterwave_multi_country",
        "sfdp_lane2_pilot_corridors",
    ):
        if rid not in register:
            findings.append(f"register missing {rid}")

    if findings:
        print("verify_dual_engine_financial_program: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_dual_engine_financial_program: DUAL_ENGINE_FINANCIAL_PROGRAM_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
