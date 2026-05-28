#!/usr/bin/env python3
"""Assert Lane 2 / BLOCKED_EXTERNAL items are documented and not falsely marked DONE."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "generated" / "lane2_external_blockers.json"
SOT = ROOT / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"


def main() -> int:
    findings: list[str] = []

    if not LEDGER.is_file():
        findings.append("missing docs/generated/lane2_external_blockers.json")
    else:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        b1175 = (data.get("batches") or {}).get("1175") or {}
        if b1175.get("lane2_status") != "NOT_STARTED_EXTERNAL":
            findings.append("1175 must remain NOT_STARTED_EXTERNAL in ledger")
        if b1175.get("repo_status") != "PARTIAL_REPO_INTAKE":
            findings.append("1175 repo_status must be PARTIAL_REPO_INTAKE")

    if SOT.is_file():
        text = SOT.read_text(encoding="utf-8")
        m = re.search(
            r"batch 1175[^\n]*\n[^\n]*\*\*([^\*]+)\*\*",
            text,
            re.IGNORECASE,
        )
        if m:
            status = m.group(1).strip().upper()
            if status.startswith("DONE"):
                findings.append("SOT batch 1175 must not be DONE (Lane 2 external)")
            if "PILOT CLOSED" in status and "NOT" not in status:
                findings.append("SOT batch 1175 must not claim PILOT CLOSED without evidence")

    pilot_evidence = sorted((ROOT / "var/evidence/geos-99/pilot/gilead-school").glob("intake_ready_*.json"))
    if not pilot_evidence:
        findings.append("missing pilot intake_ready evidence JSON")

    if findings:
        print("verify_lane2_external_honesty: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_lane2_external_honesty: LANE2_EXTERNAL_HONESTY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
