#!/usr/bin/env python3
"""SFDP scaffold gate — batches 1420+ program contract (Lane 1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    findings: list[str] = []

    plan = ROOT / "docs/plans/SOVEREIGN_FINANCIAL_DELIVERY_PLATFORM_PLAN.md"
    if not plan.is_file():
        findings.append("missing docs/plans/SOVEREIGN_FINANCIAL_DELIVERY_PLATFORM_PLAN.md")

    psp_registry = _text("apps/billing/psp_adapter_registry.py")
    if "PSP_REGISTER" not in psp_registry:
        findings.append("psp_adapter_registry missing PSP_REGISTER")

    catalog_py = _text("apps/finance/payment_region_catalog.py")
    if "CANONICAL_PAYMENT_ORCHESTRATION_ISO2" not in catalog_py:
        findings.append("payment_region_catalog missing CANONICAL_PAYMENT_ORCHESTRATION_ISO2")
    elif "frozenset" not in catalog_py and "CM" not in catalog_py:
        findings.append("payment_region_catalog ISO2 set appears empty")

    json_path = ROOT / "apps/finance/data/regional_payment_profiles.json"
    if not json_path.is_file():
        findings.append("missing apps/finance/data/regional_payment_profiles.json")
    else:
        try:
            json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(f"regional_payment_profiles.json invalid JSON: {exc}")

    types_py = _text("apps/platform_runtime/offline_action_types.py")
    if "PAYMENT_PROOF" not in types_py:
        findings.append("offline_action_types missing PAYMENT_PROOF")

    if "webhook_ingress" not in _text("apps/finance/webhook_ingress.py"):
        findings.append("webhook_ingress module incomplete")

    for rel in (
        "apps/finance/payment_provision.py",
        "apps/finance/subscription_gate.py",
        "apps/finance/webhooks/normalizer.py",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    apps_root = ROOT / "apps"
    if apps_root.is_dir():
        for path in apps_root.rglob("*.py"):
            if "pouchdb" in path.read_text(encoding="utf-8", errors="replace").lower():
                findings.append(f"PouchDB reference forbidden: {path.relative_to(ROOT)}")
                break

    static_fin = ROOT / "static/js"
    if static_fin.is_dir():
        for path in static_fin.rglob("*.js"):
            body = path.read_text(encoding="utf-8", errors="replace").lower()
            if "pouchdb" in body:
                findings.append(f"PouchDB reference in static JS: {path.relative_to(ROOT)}")
                break

    if findings:
        print("verify_sovereign_financial_delivery_scaffold: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_sovereign_financial_delivery_scaffold: SOVEREIGN_FINANCIAL_DELIVERY_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
