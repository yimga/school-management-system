#!/usr/bin/env python3
"""Master completion gate for the global governance audit program."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REGISTER_PATH = REPO / "docs" / "generated" / "global_governance_completion_register.json"
OUT_PATH = REPO / "docs" / "generated" / "global_governance_plan_completion_audit.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

VALID_STATUSES = frozenset({"NOT_DONE", "IN_PROGRESS", "DONE", "EXTERNAL_BLOCKED"})
VALID_LANES = frozenset({"GEO", "LOCALE", "GOV", "RUNTIME", "PRODUCT", "FINANCE", "EMIS", "OPS", "AUDIT"})
EXTERNAL_ALLOWLIST = frozenset(
    {
        "counsel_legal",
        "live_psp_credentials",
        "physical_infra_deploy",
        "operator_signoff",
    }
)

PHASE_ORDER: dict[str, int] = {
    "0A": 0,
    "0B": 1,
    "0C": 2,
    "0D": 3,
    "1": 4,
    "2A": 5,
    "2B": 6,
    "2C": 7,
    "3A": 8,
    "3B": 9,
    "3C": 10,
    "3D": 11,
    "3E": 12,
    "4A": 13,
    "4B": 14,
    "4C": 15,
    "4D": 16,
    "4E": 17,
    "4F": 18,
    "4G": 19,
    "5": 20,
    "CROSS": 99,
}

REQUIRED_VERIFIERS = (
    "verify_country_governance_matrix.py",
    "verify_country_dissection_ledger.py",
    "verify_country_layer_consistency.py",
    "verify_governance_doc_truth.py",
    "verify_hierarchy_silo_drift.py",
    "verify_governance_no_hardcode.py",
    "verify_school_operating_modes.py",
    "verify_global_operational_blind_spots.py",
    "verify_subdivision_coverage.py",
)


def _phase_index(phase: str) -> int:
    return PHASE_ORDER.get(str(phase or "").strip(), 999)


def _load_register() -> dict[str, Any]:
    if not REGISTER_PATH.is_file():
        raise FileNotFoundError(f"missing register: {REGISTER_PATH.relative_to(REPO)}")
    return json.loads(REGISTER_PATH.read_text(encoding="utf-8"))


def _validate_item(item: dict[str, Any], failures: list[str]) -> None:
    item_id = str(item.get("id") or "")
    phase = str(item.get("phase") or "")
    lane = str(item.get("agent_lane") or "")
    status = str(item.get("status") or "")
    proof = str(item.get("proof") or "").strip()

    if not item_id:
        failures.append("register item missing id")
        return
    if not phase:
        failures.append(f"{item_id}: missing phase")
    if lane not in VALID_LANES:
        failures.append(f"{item_id}: invalid agent_lane {lane!r}")
    if status not in VALID_STATUSES:
        failures.append(f"{item_id}: invalid status {status!r}")
    if not proof:
        failures.append(f"{item_id}: missing proof")
    if status == "EXTERNAL_BLOCKED":
        reason = str(item.get("blocked_reason") or "").strip()
        if not reason:
            failures.append(f"{item_id}: EXTERNAL_BLOCKED without blocked_reason")
        elif reason not in EXTERNAL_ALLOWLIST:
            failures.append(f"{item_id}: blocked_reason {reason!r} not in allowlist")
        sot = item.get("sot_batch")
        if not sot:
            failures.append(f"{item_id}: EXTERNAL_BLOCKED without sot_batch ref")


def _check_p0a_artifacts(failures: list[str]) -> None:
    paths = [
        REPO / "docs" / "generated" / "country_governance_matrix.json",
        REPO / "docs" / "generated" / "country_dissection_ledger.json",
        REPO / "scripts" / "generate_global_governance_bootstrap.py",
    ]
    for path in paths:
        if not path.is_file():
            failures.append(f"missing artifact: {path.relative_to(REPO)}")
    for script in REQUIRED_VERIFIERS:
        path = REPO / "scripts" / script
        if not path.is_file():
            failures.append(f"missing verifier: scripts/{script}")
    workflow = REPO / ".github" / "workflows" / "architectural-boundaries.yml"
    if workflow.is_file():
        text = workflow.read_text(encoding="utf-8")
        if "global-governance-plan-completion" not in text:
            failures.append("CI job global-governance-plan-completion not wired")
    else:
        failures.append("missing .github/workflows/architectural-boundaries.yml")


def main() -> int:
    parser = argparse.ArgumentParser(description="Global governance plan completion gate")
    parser.add_argument("--strict", action="store_true", help="Require 100%% DONE or EXTERNAL_BLOCKED")
    parser.add_argument("--phase-max", default="", help="Require all items with phase <= this phase to be DONE")
    parser.add_argument("--json", action="store_true", help="Write audit JSON")
    args = parser.parse_args()

    failures: list[str] = []
    try:
        register = _load_register()
    except FileNotFoundError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    items = register.get("items") or []
    if not items:
        failures.append("register has zero items")

    ids_seen: set[str] = set()
    for item in items:
        item_id = str(item.get("id") or "")
        if item_id in ids_seen:
            failures.append(f"duplicate register id: {item_id}")
        ids_seen.add(item_id)
        _validate_item(item, failures)

    phase_max = str(args.phase_max or "").strip()
    phase_max_idx = _phase_index(phase_max) if phase_max else None

    open_items: list[str] = []
    for item in items:
        status = str(item.get("status") or "NOT_DONE")
        item_id = str(item.get("id") or "")
        phase = str(item.get("phase") or "")

        if args.strict:
            if status in {"NOT_DONE", "IN_PROGRESS", "PARTIAL"}:
                open_items.append(f"{item_id} ({status})")
        elif phase_max_idx is not None:
            if _phase_index(phase) <= phase_max_idx and status not in {"DONE", "EXTERNAL_BLOCKED"}:
                open_items.append(f"{item_id} phase={phase} ({status})")

    if open_items:
        failures.extend([f"incomplete: {line}" for line in open_items[:40]])
        if len(open_items) > 40:
            failures.append(f"... and {len(open_items) - 40} more incomplete items")

    if phase_max == "0A" or args.strict:
        _check_p0a_artifacts(failures)

    verdict = "GLOBAL_GOVERNANCE_PLAN_COMPLETION_PASS" if not failures else "GLOBAL_GOVERNANCE_PLAN_COMPLETION_FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "mode": "strict" if args.strict else (f"phase-max={phase_max}" if phase_max else "schema-only"),
        "register_item_count": len(items),
        "status_counts": register.get("status_counts") or {},
        "failures": failures,
    }

    if args.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"\nverify_global_governance_plan_completion: {verdict}", file=sys.stderr)
        for line in failures[:30]:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_global_governance_plan_completion: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
