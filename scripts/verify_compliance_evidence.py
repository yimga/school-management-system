#!/usr/bin/env python3
"""
Verify compliance evidence ledger: required files exist (repo-local, deterministic).

Exit 1 if:
- ledger JSON missing or invalid
- any referenced path under ``evidence``, ``required_policy_docs``, ``framework_docs``,
  ``scaling_docs``, or ``operationalization_docs`` is missing

Exit 0 otherwise. Does not assert SOC2 certification.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "generated" / "compliance_evidence_ledger.json"


def _collect_paths(data: dict) -> list[str]:
    out: list[str] = []
    for key in ("required_policy_docs", "framework_docs", "scaling_docs", "operationalization_docs"):
        for p in data.get(key) or []:
            if isinstance(p, str):
                out.append(p)
    for item in data.get("evidence") or []:
        if isinstance(item, dict):
            p = item.get("path")
            if isinstance(p, str):
                out.append(p)
    return out


def main() -> int:
    if not LEDGER.is_file():
        print(f"verify_compliance_evidence: FAIL missing {LEDGER}", file=sys.stderr)
        return 1
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"verify_compliance_evidence: FAIL bad JSON: {exc}", file=sys.stderr)
        return 1
    if int(data.get("schema_version") or 0) < 1:
        print("verify_compliance_evidence: FAIL schema_version", file=sys.stderr)
        return 1
    missing: list[str] = []
    for rel in sorted(set(_collect_paths(data))):
        path = ROOT / Path(rel)
        if not path.is_file():
            missing.append(rel)
    if missing:
        print(
            "verify_compliance_evidence: FAIL missing paths:\n  "
            + "\n  ".join(missing),
            file=sys.stderr,
        )
        return 1
    print("verify_compliance_evidence: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
