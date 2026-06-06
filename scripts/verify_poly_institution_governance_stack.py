#!/usr/bin/env python3
"""Poly-institution / multi-tenant governance stack bundle gate.

Covers Organization overlay, group console, MAT hub sync, Phase 4 granular ops,
and tenant-isolation adjacency checks for the poly-institution program.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "poly_institution_governance_stack_audit.json"

REQUIRED_MODULES = (
    "apps/governance/models.py",
    "apps/governance/mat_groups_sync.py",
    "apps/governance/backfill_organizations.py",
    "apps/governance/management/commands/backfill_organizations_from_hierarchy.py",
    "apps/schools/group_console.py",
    "apps/schools/views_group_console.py",
    "apps/schools/mat_group_hub.py",
    "apps/billing/group_consolidation.py",
    "emis/org_aggregate.py",
    "apps/interop/transfer_apply.py",
    "apps/people/staff_compliance.py",
    "apps/communication/sms_router.py",
    "apps/governance/fast_switch.py",
    "apps/academics/fractional_capacity.py",
    "apps/academics/instruction_day_ledger.py",
    "apps/siteconfig/operational_time.py",
    "apps/portal/views_multicampus_billing.py",
    "apps/portal/views_multicampus_academics.py",
    "apps/portal/views_multicampus_extension.py",
)

SUBPROCESS_SCRIPTS = (
    ("verify_hierarchy_silo_drift.py", []),
    ("verify_global_operational_blind_spots.py", ["--granular-ops"]),
    ("verify_school_operating_modes.py", []),
    ("verify_org_lifecycle_events.py", []),
    ("verify_governance_doc_truth.py", []),
    ("verify_org_backfill_operator_smoke.py", []),
    ("verify_scheduling_exclude_constraints.py", []),
    ("verify_group_console_http_contract.py", []),
    ("verify_multicampus_wedge_http_contract.py", []),
)


def _run_script(name: str, extra_args: list[str], *, timeout: int = 300) -> tuple[bool, str]:
    cmd = [sys.executable, str(REPO / "scripts" / name), *extra_args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode == 0, tail[-300:] if tail else ""


def _fractional_capacity_smoke() -> tuple[bool, str]:
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from apps.academics.fractional_capacity import (
            cross_campus_allocation_ok,
            effective_room_capacity,
        )

        room = SimpleNamespace(capacity=20, capacity_fraction="0.5")
        seats = effective_room_capacity(room)
        ok = cross_campus_allocation_ok(
            existing_fraction=Decimal("0.3"),
            requested_fraction=Decimal("0.5"),
        )
        if seats != Decimal("10.00") or not ok:
            return False, f"unexpected smoke result seats={seats} ok={ok}"
        return True, "effective_room_capacity + cross_campus_allocation_ok"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Poly-institution governance stack gate")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    checks: list[dict[str, str]] = []

    for rel in REQUIRED_MODULES:
        path = REPO / rel
        if path.is_file():
            checks.append({"id": rel, "status": "PASS"})
        else:
            failures.append(f"missing module: {rel}")
            checks.append({"id": rel, "status": "FAIL"})

    ok, proof = _fractional_capacity_smoke()
    checks.append({"id": "fractional_capacity_smoke", "status": "PASS" if ok else "FAIL", "proof": proof})
    if not ok:
        failures.append(f"fractional_capacity smoke failed: {proof}")

    http_scripts = {
        "verify_group_console_http_contract.py",
        "verify_multicampus_wedge_http_contract.py",
        "verify_org_backfill_operator_smoke.py",
    }
    for script, extra in SUBPROCESS_SCRIPTS:
        timeout = 900 if script in http_scripts else 300
        ok, proof = _run_script(script, extra, timeout=timeout)
        checks.append(
            {
                "id": script,
                "status": "PASS" if ok else "FAIL",
                "proof": proof,
            }
        )
        if not ok:
            failures.append(f"{script} failed: {proof}")

    verdict = (
        "POLY_INSTITUTION_GOVERNANCE_STACK_PASS"
        if not failures
        else "POLY_INSTITUTION_GOVERNANCE_STACK_FAIL"
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "checks": checks,
        "failures": failures,
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"verify_poly_institution_governance_stack: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_poly_institution_governance_stack: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
