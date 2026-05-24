#!/usr/bin/env python3
"""SFDP program completion gate — all Lane 1 waves 1422-1431."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WAVE_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("1422 provision bind", "apps/finance/payment_provision.py"),
    ("1422 provision tests", "apps/finance/tests/test_payment_provision_bind.py"),
    ("1423 catalog drift", "apps/finance/tests/test_regional_payment_profiles_catalog_drift.py"),
    ("1424 bursar queue view", "apps/finance/views_offline_bursar_queue.py"),
    ("1424 bursar template", "templates/finance/offline_payment_intent_queue.html"),
    ("1425 subscription gate", "apps/finance/subscription_gate.py"),
    ("1425 gate tests", "apps/finance/tests/test_finance_subscription_gate.py"),
    ("1427 NG evidence", "var/evidence/geos-99/psp/paystack/README.md"),
    ("1429 CM evidence", "var/evidence/geos-99/psp/flutterwave/README.md"),
    ("1430 webhook normalizer", "apps/finance/webhooks/normalizer.py"),
    ("1430 normalizer tests", "apps/finance/tests/test_webhook_normalizer.py"),
    ("1431 payment intent", "apps/finance/payment_notification_intent.py"),
    ("1431 intent tests", "apps/finance/tests/test_payment_notification_intent.py"),
)


def main() -> int:
    findings: list[str] = []
    for label, rel in WAVE_ARTIFACTS:
        if not (ROOT / rel).is_file():
            findings.append(f"{label}: missing {rel}")

    scaffold = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_sovereign_financial_delivery_scaffold.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if scaffold.returncode != 0:
        findings.append("scaffold verifier failed")
        if scaffold.stderr:
            findings.append(scaffold.stderr.strip()[:500])

    sot = (ROOT / "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md").read_text(
        encoding="utf-8", errors="replace"
    )
    for batch in range(1420, 1432):
        needle = f"batch {batch}"
        if needle not in sot.lower():
            findings.append(f"SOT missing §11.4 row for {needle}")

    if findings:
        print("verify_sovereign_financial_delivery_completion: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_sovereign_financial_delivery_completion: SOVEREIGN_FINANCIAL_DELIVERY_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
