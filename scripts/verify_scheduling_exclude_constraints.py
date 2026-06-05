#!/usr/bin/env python3
"""Scheduling DB conflict constraints verifier (Phase 4E / EXCLUDE-adjacent).

Discrete TimeSlot booking uses partial ``UniqueConstraint`` rows on
``ScheduleEntry`` (term + teacher/room + time_slot [+ instruction_shift]).
Overlapping-interval ``EXCLUDE USING gist`` is deferred until continuous
time-range slots ship; this gate prevents regression of the denorm + constraints.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "scheduling_exclude_constraints_audit.json"
SCHEDULING = REPO / "apps" / "academics" / "scheduling.py"
MIGRATION = REPO / "apps" / "academics" / "migrations" / "0055_scheduleentry_db_conflict_constraints.py"

REQUIRED_CONSTRAINT_NAMES = (
    "uniq_schedentry_teacher_slot_shift",
    "uniq_schedentry_teacher_slot_termwide",
    "uniq_schedentry_room_slot_shift",
    "uniq_schedentry_room_slot_termwide",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduling exclude-adjacent constraints gate")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    checks: list[dict[str, str]] = []

    if not SCHEDULING.is_file():
        failures.append("missing apps/academics/scheduling.py")
    else:
        text = SCHEDULING.read_text(encoding="utf-8")
        for name in REQUIRED_CONSTRAINT_NAMES:
            ok = name in text
            checks.append({"id": f"model:{name}", "status": "PASS" if ok else "FAIL"})
            if not ok:
                failures.append(f"ScheduleEntry missing constraint {name}")
        for needle in ("def _sync_scope_from_schedule", "instruction_shift", "term = models.ForeignKey"):
            ok = needle in text
            checks.append({"id": f"scheduling:{needle}", "status": "PASS" if ok else "FAIL"})
            if not ok:
                failures.append(f"scheduling.py missing {needle!r}")

    if not MIGRATION.is_file():
        failures.append("missing migration 0055_scheduleentry_db_conflict_constraints.py")
        checks.append({"id": "migration:0055", "status": "FAIL"})
    else:
        mig = MIGRATION.read_text(encoding="utf-8")
        checks.append({"id": "migration:0055", "status": "PASS"})
        for name in REQUIRED_CONSTRAINT_NAMES:
            ok = name in mig
            checks.append({"id": f"migration:{name}", "status": "PASS" if ok else "FAIL"})
            if not ok:
                failures.append(f"migration 0055 missing constraint {name}")

    verdict = (
        "SCHEDULING_EXCLUDE_CONSTRAINTS_PASS"
        if not failures
        else "SCHEDULING_EXCLUDE_CONSTRAINTS_FAIL"
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "checks": checks,
        "failures": failures,
        "note": "Partial unique constraints on discrete TimeSlot; gist EXCLUDE deferred.",
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"verify_scheduling_exclude_constraints: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_scheduling_exclude_constraints: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
