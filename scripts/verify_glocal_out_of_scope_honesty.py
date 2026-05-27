#!/usr/bin/env python3
"""Ensure glocal program does not over-claim external-only capabilities in SOT."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOT = ROOT / "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
EVIDENCE = ROOT / "var/evidence/geos-99/compliance/residency_latest.json"
REGISTER = ROOT / "docs/external_dependencies_register.json"

BANNED_SOT_PHRASES = (
    "automatic AWS shard",
    "true CRDT",
    "CRDT merge engine",
    "BLE proximity",
    "OCR gradebook",
)

REQUIRED_HONEST_PHRASES = (
    "Lane 2",
    "operator",
    "REJECTED",
    "queued offline sync",
)


def main() -> int:
    findings: list[str] = []

    if not SOT.is_file():
        findings.append("missing SOT")
    else:
        sot = SOT.read_text(encoding="utf-8")
        batch_start = sot.find("batch 1537")
        batch_slice = sot[batch_start : batch_start + 2500] if batch_start >= 0 else ""
        for phrase in BANNED_SOT_PHRASES:
            if phrase.lower() in batch_slice.lower():
                findings.append(f"SOT batch 1537 contains banned claim: {phrase}")
        for phrase in REQUIRED_HONEST_PHRASES:
            if phrase not in batch_slice:
                findings.append(f"SOT batch 1537 missing honesty phrase: {phrase}")

    evidence_path = EVIDENCE
    if not evidence_path.is_file():
        legacy = ROOT / "var/evidence/geos-99/compliance/residency_2026-05-27.json"
        if legacy.is_file():
            evidence_path = legacy
        else:
            findings.append("missing var/evidence/geos-99/compliance/residency_latest.json")
            evidence_path = None
    if evidence_path is not None:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        if payload.get("second_physical_region_live") is True:
            findings.append("residency evidence claims second_physical_region_live=true")

    if REGISTER.is_file():
        reg = json.loads(REGISTER.read_text(encoding="utf-8"))
        entries = []
        for section in reg.get("sections") or []:
            entries.extend(section.get("entries") or [])
        ids = {str(e.get("id") or "") for e in entries}
        for required_id in (
            "glocal-second-postgres-region",
            "glocal-ble-ocr-zero-input",
            "glocal-crdt-mesh",
        ):
            if required_id not in ids:
                findings.append(f"external_dependencies_register missing {required_id}")

    if findings:
        print("verify_glocal_out_of_scope_honesty: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_glocal_out_of_scope_honesty: GLOCAL_OUT_OF_SCOPE_HONESTY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
