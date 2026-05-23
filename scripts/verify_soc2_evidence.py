#!/usr/bin/env python3
"""GEOS Lane 2 ingest: verify SOC2 (or comparable) attestation evidence is on file.

Honest contract:
  * No SOC2_EVIDENCE_PATH → `external_pending` evidence, exit 0.
  * SOC2_EVIDENCE_PATH set, file missing → `external_pending`, exit 1 under --strict.
  * File present, valid JSON with required fields (auditor, attestation_type,
    report_period_end, attestation_status) → `verified_live` IFF
    attestation_status is in the trusted-pass set
    {"type_2_passed", "type_1_passed", "iso27001_certified", "passed"}, else
    `external_pending`.

Evidence is written to `var/lane2-evidence/soc2.json` (operator's path is the
INPUT, not the output). The GEOS matrix reads
`docs/external_dependencies_register.json` for `verified_live` — operator
reviews evidence and manually flips the `soc2_pci_placeholder` entry.

Operator-supplied evidence JSON must contain at minimum:
    {
        "auditor": "<auditor firm name>",
        "attestation_type": "SOC2 Type 2" | "SOC2 Type 1" | "ISO 27001" | ...,
        "report_period_end": "YYYY-MM-DD",
        "attestation_status": "type_2_passed" | "type_1_passed" | "iso27001_certified" | "passed" | "in_progress" | "remediation_required",
        "signed_by": "<lead auditor full name>",
        "report_uri": "<internal vault link to signed PDF>"
    }

The actual PDF report lives in operator's secure vault; this script only
validates the metadata pointer. Operator workflow:

    export SOC2_EVIDENCE_PATH=/secure/audit/2026-Q2-soc2-type2.json
    python scripts/verify_soc2_evidence.py
    # → reads evidence, decides whether to flip register

Usage:
    python scripts/verify_soc2_evidence.py [--strict]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "var" / "lane2-evidence"
EVIDENCE_PATH = EVIDENCE_DIR / "soc2.json"

REQUIRED_FIELDS = (
    "auditor",
    "attestation_type",
    "report_period_end",
    "attestation_status",
    "signed_by",
    "report_uri",
)
TRUSTED_PASS_STATUSES = frozenset(
    {"type_2_passed", "type_1_passed", "iso27001_certified", "passed"}
)


def _write_evidence(payload: dict) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _validate(evidence: dict) -> tuple[bool, list[str]]:
    missing = [f for f in REQUIRED_FIELDS if not evidence.get(f)]
    return (not missing), missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when path absent / file missing / fields incomplete.",
    )
    args = parser.parse_args()

    path_str = os.environ.get("SOC2_EVIDENCE_PATH")
    now = datetime.now(timezone.utc).isoformat()

    if not path_str:
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": "env_absent",
            "missing_env": ["SOC2_EVIDENCE_PATH"],
            "register_pillar": "aws",  # compliance lives under AWS pillar in matrix
            "register_section_id": "compliance_certifications",
        }
        _write_evidence(payload)
        print("verify_soc2_evidence: external_pending (no SOC2_EVIDENCE_PATH)")
        return 1 if args.strict else 0

    operator_path = Path(path_str)
    if not operator_path.is_file():
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": "evidence_file_not_found",
            "operator_path": str(operator_path),
            "register_pillar": "aws",
            "register_section_id": "compliance_certifications",
        }
        _write_evidence(payload)
        print(f"verify_soc2_evidence: external_pending (file not found at {operator_path})")
        return 1 if args.strict else 0

    try:
        evidence = json.loads(operator_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": f"evidence_file_unreadable: {exc}",
            "operator_path": str(operator_path),
            "register_pillar": "aws",
            "register_section_id": "compliance_certifications",
        }
        _write_evidence(payload)
        print(f"verify_soc2_evidence: external_pending (unreadable: {exc})")
        return 1 if args.strict else 0

    if not isinstance(evidence, dict):
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": "evidence_must_be_json_object",
            "operator_path": str(operator_path),
            "register_pillar": "aws",
            "register_section_id": "compliance_certifications",
        }
        _write_evidence(payload)
        print("verify_soc2_evidence: external_pending (evidence is not a JSON object)")
        return 1 if args.strict else 0

    valid, missing = _validate(evidence)
    status_value = (evidence.get("attestation_status") or "").lower()
    trusted = status_value in TRUSTED_PASS_STATUSES

    if not valid:
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": "evidence_fields_incomplete",
            "missing_fields": missing,
            "operator_path": str(operator_path),
            "register_pillar": "aws",
            "register_section_id": "compliance_certifications",
        }
        _write_evidence(payload)
        print(f"verify_soc2_evidence: external_pending (missing fields: {','.join(missing)})")
        return 1 if args.strict else 0

    payload = {
        "generated_at": now,
        "status": "verified_live" if trusted else "external_pending",
        "reason": (
            "trusted_pass_attestation"
            if trusted
            else f"attestation_status_not_trusted: {status_value}"
        ),
        "evidence_summary": {
            "auditor": evidence.get("auditor"),
            "attestation_type": evidence.get("attestation_type"),
            "report_period_end": evidence.get("report_period_end"),
            "attestation_status": evidence.get("attestation_status"),
            "signed_by": evidence.get("signed_by"),
            # NOTE: report_uri intentionally NOT mirrored into repo evidence
            # — that's the operator's secure-vault pointer and should not
            # leave their boundary. Source path + checksum stay operator-side.
        },
        "operator_path": str(operator_path),
        "register_pillar": "aws",
        "register_section_id": "compliance_certifications",
    }
    _write_evidence(payload)

    if trusted:
        print(
            f"verify_soc2_evidence: verified_live "
            f"({evidence.get('attestation_type')} signed by {evidence.get('signed_by')})"
        )
        return 0
    print(
        f"verify_soc2_evidence: external_pending "
        f"(attestation_status='{status_value}' not in trusted-pass set)"
    )
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
