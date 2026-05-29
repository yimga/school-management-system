#!/usr/bin/env python3
"""Governance documentation truth gate — Campus, EMIS, MAT hub claims vs code."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "governance_doc_truth_audit.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Governance doc truth verifier")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-pending", action="store_true", help="Phase 0B scaffold — structural checks only")
    args = parser.parse_args()

    checks: list[dict[str, str]] = []
    failures: list[str] = []

    campus_model = REPO / "apps" / "schoolops" / "models.py"
    campus_doc = REPO / "docs" / "SCHOOL_TENANT_CAMPUS_CANONICAL.md"
    mat_doc = REPO / "docs" / "MAT_GROUP_HUB.md"
    mat_hub = REPO / "apps" / "schools" / "mat_group_hub.py"

    if campus_model.is_file() and "class Campus" in campus_model.read_text(encoding="utf-8"):
        checks.append({"id": "campus-model-exists", "status": "PASS"})
    else:
        failures.append("schoolops.Campus model not found")
        checks.append({"id": "campus-model-exists", "status": "FAIL"})

    if campus_doc.is_file():
        text = campus_doc.read_text(encoding="utf-8").lower()
        if "future" in text and "campus" in text and "not" not in text[:200]:
            if not args.allow_pending:
                failures.append("SCHOOL_TENANT_CAMPUS_CANONICAL.md still claims Campus is future")
                checks.append({"id": "campus-doc-truth", "status": "FAIL"})
            else:
                checks.append({"id": "campus-doc-truth", "status": "PENDING"})
        else:
            checks.append({"id": "campus-doc-truth", "status": "PASS"})
    else:
        failures.append("missing SCHOOL_TENANT_CAMPUS_CANONICAL.md")
        checks.append({"id": "campus-doc-truth", "status": "FAIL"})

    if mat_hub.is_file():
        checks.append({"id": "mat-hub-code", "status": "PASS"})
    else:
        failures.append("mat_group_hub.py missing")
        checks.append({"id": "mat-hub-code", "status": "FAIL"})

    if mat_doc.is_file():
        checks.append({"id": "mat-hub-doc", "status": "PASS"})
    else:
        if args.allow_pending:
            checks.append({"id": "mat-hub-doc", "status": "PENDING"})
        else:
            failures.append("MAT_GROUP_HUB.md missing")
            checks.append({"id": "mat-hub-doc", "status": "FAIL"})

    mandate = REPO / "docs" / "GLOBAL_GOVERNANCE_MANDATE_CROSSWALK.md"
    if mandate.is_file():
        checks.append({"id": "mandate-crosswalk", "status": "PASS"})
    elif args.allow_pending:
        checks.append({"id": "mandate-crosswalk", "status": "PENDING"})
    else:
        failures.append("GLOBAL_GOVERNANCE_MANDATE_CROSSWALK.md missing")
        checks.append({"id": "mandate-crosswalk", "status": "FAIL"})

    verdict = "GOVERNANCE_DOC_TRUTH_PASS" if not failures else "GOVERNANCE_DOC_TRUTH_FAIL"
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
        print(f"verify_governance_doc_truth: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_governance_doc_truth: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
