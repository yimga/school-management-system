#!/usr/bin/env python3
"""CEZGP batch 1515 — parent pay-all finance gate."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    view = ROOT / "apps/portal/views_parent_finance.py"
    urls = ROOT / "apps/portal/urls.py"
    tpl_finance = ROOT / "templates/parent/finance.html"
    tpl_confirm = ROOT / "templates/parent/finance_pay_all_confirm.html"
    registry = ROOT / "apps/platform_runtime/workflow_registry.py"
    tests = ROOT / "apps/portal/tests/test_parent_finance_pay_all.py"

    for path in (view, urls, tpl_finance, tpl_confirm, registry, tests):
        if not path.is_file():
            findings.append(f"missing {path.relative_to(ROOT)}")

    if view.is_file():
        body = view.read_text(encoding="utf-8")
        for needle in (
            "aggregate_family_balance",
            "propose_payment_split",
            "parent_finance_pay_all",
            "dispatch_payment_received_intent",
            "get_normalized_regional_profile",
        ):
            if needle not in body:
                findings.append(f"views_parent_finance.py missing {needle}")

    if urls.is_file() and "parent_finance_pay_all" not in urls.read_text(encoding="utf-8"):
        findings.append("urls.py missing parent_finance_pay_all route")

    if tpl_finance.is_file():
        fin = tpl_finance.read_text(encoding="utf-8")
        if "Pay all open balances" not in fin and "pay_all_url" not in fin:
            findings.append("finance.html missing pay-all hero")
        if "wallet" not in fin.lower():
            findings.append("finance.html missing wallet block")

    if tpl_confirm.is_file() and "regional_payment" not in tpl_confirm.read_text(encoding="utf-8"):
        findings.append("finance_pay_all_confirm.html missing regional hints")

    if registry.is_file() and '"parent-portal-pay-all"' not in registry.read_text(encoding="utf-8"):
        findings.append("workflow_registry missing parent-portal-pay-all")

    if tests.is_file():
        try:
            ast.parse(tests.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            findings.append(f"test_parent_finance_pay_all.py syntax: {exc}")

    if findings:
        print("verify_parent_finance_pay_all: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_parent_finance_pay_all: PARENT_FINANCE_PAY_ALL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
