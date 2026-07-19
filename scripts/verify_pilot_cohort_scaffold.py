#!/usr/bin/env python3
"""Verify S8 pilot cohort scaffold — playbook + register existence and schema.

PASS when:
  - docs/PILOT_COHORT_PLAYBOOK.md exists with selection criteria
  - docs/generated/pilot_cohort_register.json exists with valid schema

Reports EXTERNAL_PILOT_UNSIGNED when:
  - No entry in the register has signed=true (no real cohort member yet)

Exit 0 = scaffold is sound. EXTERNAL classification is honest about what
remains a human/business task.

Run: python scripts/verify_pilot_cohort_scaffold.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PLAYBOOK_PATH = ROOT / "docs" / "PILOT_COHORT_PLAYBOOK.md"
REGISTER_PATH = ROOT / "docs" / "generated" / "pilot_cohort_register.json"

REQUIRED_SCHEMA_KEYS = {"schema_version", "cohort_id", "entries", "metadata"}
REQUIRED_ENTRY_KEYS = {"school_slug", "signed", "status"}
VALID_STATUSES = {
    "candidate", "qualified", "signed", "provisioned", "active", "churned", "graduated"
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    checks: list[dict] = []
    external: list[str] = []

    # 1. Playbook exists
    playbook_exists = PLAYBOOK_PATH.is_file()
    checks.append({
        "check": "playbook_exists",
        "pass": playbook_exists,
        "detail": "docs/PILOT_COHORT_PLAYBOOK.md present" if playbook_exists else "MISSING",
    })

    # 2. Playbook contains selection criteria
    playbook_has_criteria = False
    if playbook_exists:
        content = PLAYBOOK_PATH.read_text(encoding="utf-8")
        playbook_has_criteria = "Selection Criteria" in content
    checks.append({
        "check": "playbook_has_selection_criteria",
        "pass": playbook_has_criteria,
        "detail": (
            "Beachhead Selection Criteria section present"
            if playbook_has_criteria
            else "MISSING selection criteria"
        ),
    })

    # 3. Playbook contains activation metrics
    playbook_has_metrics = False
    if playbook_exists:
        playbook_has_metrics = "Activation Metrics" in content
    checks.append({
        "check": "playbook_has_activation_metrics",
        "pass": playbook_has_metrics,
        "detail": (
            "Activation Metrics section present"
            if playbook_has_metrics
            else "MISSING activation metrics"
        ),
    })

    # 4. Register JSON exists and is valid
    register_valid = False
    register_data = None
    if REGISTER_PATH.is_file():
        try:
            register_data = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
            if isinstance(register_data, dict):
                missing = REQUIRED_SCHEMA_KEYS - set(register_data.keys())
                register_valid = len(missing) == 0
        except (json.JSONDecodeError, OSError):
            pass
    checks.append({
        "check": "register_schema_valid",
        "pass": register_valid,
        "detail": (
            f"schema_version={register_data.get('schema_version')}, "
            f"cohort_id={register_data.get('cohort_id')}"
            if register_valid and register_data
            else "MISSING or invalid schema"
        ),
    })

    # 5. Register entries (if any) have valid shape
    entries_valid = True
    entry_count = 0
    if register_valid and register_data:
        entries = register_data.get("entries", [])
        entry_count = len(entries)
        for entry in entries:
            if not isinstance(entry, dict):
                entries_valid = False
                break
            missing_keys = REQUIRED_ENTRY_KEYS - set(entry.keys())
            if missing_keys:
                entries_valid = False
                break
            if entry.get("status") not in VALID_STATUSES:
                entries_valid = False
                break
    checks.append({
        "check": "register_entries_valid",
        "pass": entries_valid,
        "detail": f"{entry_count} entries, all valid shape" if entries_valid else "invalid entries",
    })

    # 6. Check for signed cohort member
    has_signed = False
    if register_valid and register_data:
        for entry in register_data.get("entries", []):
            if isinstance(entry, dict) and entry.get("signed") is True:
                has_signed = True
                break

    if not has_signed:
        external.append(
            "EXTERNAL_PILOT_UNSIGNED: No entry in pilot_cohort_register.json has "
            "signed=true. A real pilot cohort member requires: school identification "
            "(outbound), qualification call, agreement signing, and tenant provisioning "
            "-- all human/business tasks outside the repo."
        )

    # 7. Metadata well-formed
    metadata_ok = False
    if register_valid and register_data:
        meta = register_data.get("metadata", {})
        metadata_ok = bool(meta.get("created_at")) and bool(meta.get("playbook_path"))
    checks.append({
        "check": "register_metadata_well_formed",
        "pass": metadata_ok,
        "detail": "metadata has created_at + playbook_path" if metadata_ok else "incomplete metadata",
    })

    all_pass = all(c["pass"] for c in checks)
    report = {
        "gate": "verify_pilot_cohort_scaffold",
        "status": "PASS" if all_pass else "FAIL",
        "has_signed_entry": has_signed,
        "checks": checks,
        "external_remaining": external,
        "summary": (
            "Pilot cohort scaffold is sound (playbook + register + schema). "
            + (
                "At least one signed cohort member exists."
                if has_signed
                else "EXTERNAL_PILOT_UNSIGNED until a real school signs."
            )
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if all_pass else "FAIL"
        print(f"verify_pilot_cohort_scaffold: {status}")
        for c in checks:
            mark = "OK" if c["pass"] else "FAIL"
            print(f"  [{mark}] {c['check']}: {c['detail']}")
        if external:
            print("\n  EXTERNAL (honest classification, not a gate failure):")
            for e in external:
                print(f"    - {e}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
