#!/usr/bin/env python3
"""Verify workflow-aware offline apply module is wired."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PLATFORM_DISPATCH = (
    "apply_finance_workflow",
    "apply_payroll_workflow",
)

FINANCE_WORKFLOWS = (
    "finance_cash_closure",
    "finance_report_request",
    "finance_split_allocation",
)

PAYROLL_WORKFLOWS = (
    "payroll_create_run",
    "payroll_leave_request",
)


def main() -> int:
    findings: list[str] = []
    mod = ROOT / "apps/platform_runtime/offline_workflow_apply.py"
    queue = ROOT / "apps/platform_runtime/offline_queue.py"
    portal = ROOT / "apps/portal/views_offline_sync.py"

    if not mod.is_file():
        findings.append("missing offline_workflow_apply.py")
    else:
        text = mod.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "try_apply_field_capture_workflow",
            "substitute_handover",
            "lost_belongings_mint",
            *PLATFORM_DISPATCH,
        ):
            if needle not in text:
                findings.append(f"offline_workflow_apply missing {needle}")

    fin_mod = ROOT / "apps/finance/offline_workflow_handlers.py"
    if not fin_mod.is_file():
        findings.append("missing finance/offline_workflow_handlers.py")
    else:
        ftext = fin_mod.read_text(encoding="utf-8", errors="replace")
        if "FinanceOfflineCaptureRecord" not in ftext:
            findings.append("finance handlers missing FinanceOfflineCaptureRecord")
        for wf in FINANCE_WORKFLOWS:
            if wf not in ftext:
                findings.append(f"finance handlers missing {wf}")

    pay_mod = ROOT / "apps/payroll/offline_workflow_handlers.py"
    if not pay_mod.is_file():
        findings.append("missing payroll/offline_workflow_handlers.py")
    else:
        ptext = pay_mod.read_text(encoding="utf-8", errors="replace")
        for wf in PAYROLL_WORKFLOWS:
            if wf not in ptext:
                findings.append(f"payroll handlers missing {wf}")

    mig_fin = ROOT / "apps/finance/migrations/0065_workforce_offline_capture_1511.py"
    mig_pay = ROOT / "apps/payroll/migrations/0007_workforce_offline_capture_1511.py"
    if not mig_fin.is_file():
        findings.append("missing finance migration 0065")
    if not mig_pay.is_file():
        findings.append("missing payroll migration 0007")

    qtext = queue.read_text(encoding="utf-8", errors="replace") if queue.is_file() else ""
    if "try_apply_field_capture_workflow" not in qtext:
        findings.append("offline_queue missing workflow dispatch")
    if "_persist_student_note" not in qtext:
        findings.append("offline_queue missing _persist_student_note")

    ptext = portal.read_text(encoding="utf-8", errors="replace") if portal.is_file() else ""
    if "OfflineActionType.IAM_REQUEST_ACCESS" not in ptext:
        findings.append("api_offline_enqueue missing IAM branch")

    ctx = ROOT / "apps/siteconfig/context_processors.py"
    if "FINANCE_GLOCAL" not in ctx.read_text(encoding="utf-8", errors="replace"):
        findings.append("context_processors missing FINANCE_GLOCAL")

    partial = ROOT / "templates/partials/rmc_chart_js_self_host.html"
    if not partial.is_file():
        findings.append("missing rmc_chart_js_self_host.html partial")

    models = ROOT / "apps/schoolops/models_micro_friction.py"
    if not models.is_file():
        findings.append("missing models_micro_friction.py")
    elif "SubstituteHandoverPacketRecord" not in models.read_text(encoding="utf-8"):
        findings.append("missing SubstituteHandoverPacketRecord model")

    if findings:
        print("verify_offline_workflow_apply: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_offline_workflow_apply: OFFLINE_WORKFLOW_APPLY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
