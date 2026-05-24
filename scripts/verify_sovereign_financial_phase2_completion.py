#!/usr/bin/env python3
"""SFDP Phase 2 Lane 1 completion — batches 1432–1450 repo scope."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GATEWAYS = (
    "razorpay.py",
    "pesapal.py",
    "mercado_pago.py",
    "dlocal.py",
)
PHASE2_MODULES = (
    "apps/finance/payment_marketplace_split.py",
    "apps/finance/payment_corridor_contracts.py",
    "apps/finance/payment_lane2_status.py",
)


def main() -> int:
    findings: list[str] = []

    for name in GATEWAYS:
        if not (ROOT / "apps/finance/gateways" / name).is_file():
            findings.append(f"missing gateway {name}")

    for rel in PHASE2_MODULES:
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    urls = (ROOT / "apps/finance/urls.py").read_text(encoding="utf-8", errors="replace")
    for needle in ("offline_payment_intent_bulk_approve", "offline_payment_intent_queue_export"):
        if needle not in urls:
            findings.append(f"finance urls missing {needle}")

    data = json.loads(
        (ROOT / "apps/finance/data/regional_payment_profiles.json").read_text(encoding="utf-8")
    )
    if len(data) < 200:
        findings.append(f"regional_payment_profiles.json has {len(data)} keys, need >=200")

    sot = (ROOT / "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md").read_text(
        encoding="utf-8", errors="replace"
    )
    for batch in range(1432, 1451):
        if f"batch {batch}" not in sot.lower():
            findings.append(f"SOT missing batch {batch}")

    plan = (ROOT / "docs/plans/SOVEREIGN_FINANCIAL_DELIVERY_PLATFORM_PLAN.md").read_text(
        encoding="utf-8", errors="replace"
    )
    if "SOVEREIGN_FINANCIAL_PHASE2_COMPLETE" not in plan and "DONE (Lane 1 repo-scope)" not in plan:
        findings.append("SFDP plan Phase 2 not marked repo-complete")

    if findings:
        print("verify_sovereign_financial_phase2_completion: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_sovereign_financial_phase2_completion: SOVEREIGN_FINANCIAL_PHASE2_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
