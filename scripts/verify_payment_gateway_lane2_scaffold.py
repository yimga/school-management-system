#!/usr/bin/env python3
"""Lane 2 PSP evidence scaffold — honest operator paths (never fabricates verified_live)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []

    checklist_path = ROOT / "apps/finance/payment_lane2_checklist.py"
    if not checklist_path.is_file():
        findings.append("missing payment_lane2_checklist.py")
    else:
        text = checklist_path.read_text(encoding="utf-8", errors="replace")
        if "LANE2_PILOT_CORRIDORS" not in text:
            findings.append("LANE2_PILOT_CORRIDORS not defined")

    for subdir in ("paystack", "flutterwave", "mtn_momo", "orange_money", "stripe"):
        readme = ROOT / "var/evidence/geos-99/psp" / subdir / "README.md"
        if not readme.is_file():
            findings.append(f"missing evidence README: {readme.relative_to(ROOT)}")

    templates = (
        "var/evidence/geos-99/psp/stripe/phase1_platform_charge_evidence.template.json",
        "var/evidence/geos-99/psp/stripe/phase2_connect_pilot_evidence.template.json",
        "var/evidence/geos-99/psp/live_reconciliation_evidence.template.json",
        "var/evidence/geos-99/psp/paystack/phase1_paystack_charge_evidence.template.json",
        "var/evidence/geos-99/psp/flutterwave/phase1_flutterwave_charge_evidence.template.json",
    )
    playbook = ROOT / "scripts/run_lane2_operator_playbook.py"
    if not playbook.is_file():
        findings.append("missing scripts/run_lane2_operator_playbook.py")
    for rel in templates:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing template {rel}")
        else:
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                findings.append(f"invalid JSON template {rel}")

    register_path = ROOT / "docs/external_dependencies_register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    payments = next(
        (s for s in register.get("sections", []) if s.get("id") == "payments_psp_settlement"),
        None,
    )
    if not payments:
        findings.append("register missing payments_psp_settlement section")
    else:
        ids = {e.get("id") for e in payments.get("entries", [])}
        for rid in (
            "stripe_global_cards",
            "stripe_connect_platform",
            "paystack_wa",
            "flutterwave_multi_country",
            "mtn_momo",
            "orange_money",
            "sfdp_lane2_pilot_corridors",
        ):
            if rid not in ids:
                findings.append(f"register missing entry {rid}")
        for entry in payments.get("entries", []):
            status = entry.get("status", "")
            if status == "verified_live" and entry.get("id") in {
                "paystack_wa",
                "flutterwave_multi_country",
                "mtn_momo",
                "orange_money",
            }:
                evidence = entry.get("evidence_notes", "")
                if "operator" not in evidence.lower() and "var/evidence" not in evidence:
                    findings.append(
                        f"{entry['id']} is verified_live without evidence_notes path — dishonest"
                    )

    if findings:
        print("verify_payment_gateway_lane2_scaffold: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_payment_gateway_lane2_scaffold: PAYMENT_GATEWAY_LANE2_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
