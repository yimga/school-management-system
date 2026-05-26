#!/usr/bin/env python3
"""Phase-by-phase audit for workforce money plane batch 1511 (A–D)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "workforce_money_plane_phase_audit.json"

PHASES: dict[str, list[tuple[str, str]]] = {
    "A_finance_offline_apply": [
        ("file", "apps/finance/offline_workflow_handlers.py"),
        ("file", "apps/finance/models_offline_capture.py"),
        ("file", "apps/finance/migrations/0065_workforce_offline_capture_1511.py"),
        ("needle", "apps/platform_runtime/offline_workflow_apply.py:apply_finance_workflow"),
        ("needle", "apps/finance/offline_workflow_handlers.py:finance_cash_closure"),
        ("needle", "apps/finance/offline_workflow_handlers.py:finance_suspense_claim"),
        ("needle", "apps/finance/offline_workflow_handlers.py:finance_split_allocation"),
        ("needle", "apps/finance/offline_workflow_handlers.py:finance_report_request"),
        ("needle", "apps/finance/offline_workflow_handlers.py:FinanceOfflineCaptureRecord"),
        ("template", "templates/finance/cash_office_closure.html:data-rmc-offline-workflow"),
    ],
    "B_payroll_offline_capture": [
        ("file", "apps/payroll/offline_workflow_handlers.py"),
        ("file", "apps/payroll/models_offline_capture.py"),
        ("file", "apps/payroll/migrations/0007_workforce_offline_capture_1511.py"),
        ("needle", "apps/platform_runtime/offline_workflow_apply.py:apply_payroll_workflow"),
        ("needle", "apps/payroll/offline_workflow_handlers.py:payroll_create_run"),
        ("needle", "apps/payroll/offline_workflow_handlers.py:payroll_leave_request"),
        ("template", "templates/payroll/create_run.html:payroll_create_run"),
        ("template", "templates/payroll/employee_leave.html:payroll_leave_request"),
    ],
    "C_global_disbursement": [
        ("file", "apps/payroll/disbursement_export.py"),
        ("needle", "apps/payroll/disbursement_export.py:build_disbursement_csv"),
        ("needle", "apps/payroll/views.py:export_disbursement"),
        ("needle", "apps/payroll/urls.py:export_disbursement"),
        ("template", "templates/payroll/run_detail.html:export_disbursement"),
    ],
    "D_workforce_hub": [
        ("file", "apps/finance/views_workforce_hub.py"),
        ("file", "templates/finance/workforce_command_center.html"),
        ("needle", "apps/finance/urls.py:workforce_command_center"),
        ("needle", "templates/finance/dashboard.html:workforce_command_center"),
    ],
}


def _check(kind: str, spec: str) -> tuple[bool, str]:
    if kind == "file":
        path = ROOT / spec
        ok = path.is_file()
        return ok, str(path.relative_to(ROOT)) if ok else f"missing {spec}"
    if kind == "needle":
        path_s, needle = spec.split(":", 1)
        path = ROOT / path_s
        if not path.is_file():
            return False, f"missing {path_s}"
        text = path.read_text(encoding="utf-8", errors="replace")
        ok = needle in text
        return ok, needle if ok else f"{needle} not in {path_s}"
    if kind == "template":
        path_s, needle = spec.split(":", 1)
        path = ROOT / path_s
        if not path.is_file():
            return False, f"missing {path_s}"
        ok = needle in path.read_text(encoding="utf-8", errors="replace")
        return ok, f"{path_s} contains {needle}" if ok else f"{path_s} missing {needle}"
    return False, f"unknown check {kind}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    rows: list[dict] = []
    phase_summary: dict[str, dict] = {}

    for phase_id, checks in PHASES.items():
        phase_ok = True
        for kind, spec in checks:
            ok, proof = _check(kind, spec)
            rows.append({"phase": phase_id, "check": spec, "ok": ok, "proof": proof})
            if not ok:
                phase_ok = False
        phase_summary[phase_id] = {"ok": phase_ok, "checks": len(checks)}

    all_ok = all(p["ok"] for p in phase_summary.values())
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_id": 1511,
        "verdict": "WORKFORCE_MONEY_PLANE_PHASE_AUDIT_PASS" if all_ok else "WORKFORCE_MONEY_PLANE_PHASE_AUDIT_FAIL",
        "finding_count": sum(1 for r in rows if not r["ok"]),
        "phases": phase_summary,
        "rows": rows,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(payload["verdict"])
    for phase_id, meta in phase_summary.items():
        status = "PASS" if meta["ok"] else "FAIL"
        print(f"  {phase_id}: {status} ({meta['checks']} checks)")

    if not all_ok:
        for r in rows:
            if not r["ok"]:
                print(f"  FAIL [{r['phase']}] {r['check']}: {r['proof']}", file=sys.stderr)
        return 1
    if args.write:
        print(f"  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
