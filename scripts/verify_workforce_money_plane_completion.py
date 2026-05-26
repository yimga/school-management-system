#!/usr/bin/env python3
"""Verify HR + payroll + finance workforce money plane (batch 1511)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FINANCE_WORKFLOWS = (
    "finance_cash_closure",
    "finance_suspense_claim",
    "finance_access_bulk",
    "finance_access_request",
    "finance_generate_fees",
    "finance_split_allocation",
    "finance_report_request",
    "finance_requests_inbox",
    "finance_permission_to_pay_open",
    "finance_permission_to_pay_approve",
)

PAYROLL_WORKFLOWS = ("payroll_create_run", "payroll_leave_request")


def main() -> int:
    findings: list[str] = []

    fin_handlers = ROOT / "apps/finance/offline_workflow_handlers.py"
    pay_handlers = ROOT / "apps/payroll/offline_workflow_handlers.py"
    platform_apply = ROOT / "apps/platform_runtime/offline_workflow_apply.py"
    disburse = ROOT / "apps/payroll/disbursement_export.py"
    hub_view = ROOT / "apps/finance/views_workforce_hub.py"
    hub_tpl = ROOT / "templates/finance/workforce_command_center.html"

    for path in (fin_handlers, pay_handlers, platform_apply, disburse, hub_view, hub_tpl):
        if not path.is_file():
            findings.append(f"missing {path.relative_to(ROOT)}")

    ftext = fin_handlers.read_text(encoding="utf-8", errors="replace")
    for wf in FINANCE_WORKFLOWS:
        if wf not in ftext:
            findings.append(f"finance handler missing {wf}")

    ptext = pay_handlers.read_text(encoding="utf-8", errors="replace")
    for wf in PAYROLL_WORKFLOWS:
        if wf not in ptext:
            findings.append(f"payroll handler missing {wf}")

    papply = platform_apply.read_text(encoding="utf-8", errors="replace")
    if "apply_finance_workflow" not in papply or "apply_payroll_workflow" not in papply:
        findings.append("platform offline_workflow_apply missing finance/payroll dispatch")

    create_run = ROOT / "templates/payroll/create_run.html"
    if 'data-rmc-offline-workflow="payroll_create_run"' not in create_run.read_text(
        encoding="utf-8", errors="replace"
    ):
        findings.append("payroll create_run missing offline wiring")

    if findings:
        print("verify_workforce_money_plane_completion: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_workforce_money_plane_completion: WORKFORCE_MONEY_PLANE_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
