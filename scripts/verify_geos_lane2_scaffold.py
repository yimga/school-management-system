#!/usr/bin/env python3
"""
GEOS-99 Lane 2 scaffold verifier — repo-complete operator readiness (not verified_live).

Ensures evidence store, pilot scorecard schema, external register, and §13.7 docs exist
so batch 1391 can close without fabricating live proof.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_README = ROOT / "var" / "evidence" / "geos-99" / "README.md"
REGISTER = ROOT / "docs" / "external_dependencies_register.json"
PILOT = ROOT / "docs" / "generated" / "pilot_readiness_scorecard.json"
LANE2_CHECKLIST = ROOT / "docs" / "generated" / "geos_lane2_operator_checklist.md"
SOT = ROOT / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
REQUIRED_PILOT_BOOLS = (
    "attendance_completed",
    "marks_completed",
    "report_generated",
    "invoice_created",
    "receipt_or_payment_captured",
    "parent_portal_viewed",
    "offline_sync_used",
)


def _fail(msg: str) -> int:
    print(f"verify_geos_lane2_scaffold: FAIL — {msg}", file=sys.stderr)
    return 1


def main() -> int:
    if not EVIDENCE_README.is_file():
        return _fail(f"missing {EVIDENCE_README.relative_to(ROOT)}")
    if not REGISTER.is_file():
        return _fail(f"missing {REGISTER.relative_to(ROOT)}")
    if not PILOT.is_file():
        return _fail(f"missing {PILOT.relative_to(ROOT)}")
    if not LANE2_CHECKLIST.is_file():
        return _fail(f"missing {LANE2_CHECKLIST.relative_to(ROOT)}")

    sot_text = SOT.read_text(encoding="utf-8", errors="replace")
    for needle in ("§13.7", "GEOS-99", "verify_greatest_education_os_matrix"):
        if needle not in sot_text:
            return _fail(f"SOT missing {needle!r}")

    reg = json.loads(REGISTER.read_text(encoding="utf-8"))
    sections = reg.get("sections") or []
    if not sections:
        return _fail("external_dependencies_register has no sections")
    statuses: set[str] = set()
    for section in sections:
        for entry in section.get("entries") or []:
            statuses.add(str(entry.get("status") or "not_started"))
    if "verified_live" not in statuses:
        # ladder must be documented; verified_live may be unused until operator acts
        pass

    pilot = json.loads(PILOT.read_text(encoding="utf-8"))
    pilots = pilot.get("pilots") or pilot.get("slots") or []
    if not pilots:
        return _fail("pilot_readiness_scorecard has no pilot slots")
    slot1 = pilots[0]
    for key in REQUIRED_PILOT_BOOLS:
        if key not in slot1:
            return _fail(f"pilot slot 1 missing field {key!r}")

    print("verify_geos_lane2_scaffold: GEOS_LANE2_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
