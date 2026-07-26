#!/usr/bin/env python3
"""Scheduling DB conflict-constraint verifier (per-PLAN double-booking uniques).

``ScheduleEntry`` prevents double-booking with partial ``UniqueConstraint`` rows
scoped to the SCHEDULE (the plan), NOT the term. Phase 4E (migration 0055)
originally keyed them on ``term``, which made the SECOND Schedule for any term
impossible — every entry collided on (term, teacher|room, time_slot) — so a school
could generate its timetable exactly once, ever. Migration 0066 rescoped them to
the plan: a term legitimately holds many DRAFT/PUBLISHED plans, and
``Schedule.publish`` is what keeps the LIVE timetable non-double-booked.

This gate freezes that fix in place. It fails if:
  * a per-plan unique goes missing from the model or the rescope migration, or
  * an old term-wide/shift constraint name RETURNS to the model — re-adding one
    rescopes double-booking back to the term and resurrects the one-shot-per-term
    bug. (Historical migration 0055 still names them; that is correct — the
    negative check applies to the model only.)

Overlapping-interval ``EXCLUDE USING gist`` stays deferred until continuous
time-range slots ship.
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
MIGRATION = (
    REPO / "apps" / "academics" / "migrations" / "0066_scheduleentry_conflict_scope_per_plan.py"
)

# The per-plan uniques that MUST exist (model + the rescope migration).
REQUIRED_CONSTRAINT_NAMES = (
    "uniq_schedentry_teacher_slot_in_plan",
    "uniq_schedentry_room_slot_in_plan",
)

# The old term-scoped names that must NEVER return to the MODEL: re-adding one
# rescopes double-booking back to the term and reinstates the one-shot-per-term
# bug (a term holds many plans). They legitimately remain in historical migration
# 0055 (which added them; 0066 removed them), so this check applies to the model.
FORBIDDEN_CONSTRAINT_NAMES = (
    "uniq_schedentry_teacher_slot_termwide",
    "uniq_schedentry_room_slot_termwide",
    "uniq_schedentry_teacher_slot_shift",
    "uniq_schedentry_room_slot_shift",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduling per-plan constraints gate")
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
                failures.append(f"ScheduleEntry missing per-plan constraint {name}")
        for name in FORBIDDEN_CONSTRAINT_NAMES:
            gone = name not in text
            checks.append({"id": f"model:not:{name}", "status": "PASS" if gone else "FAIL"})
            if not gone:
                failures.append(
                    f"ScheduleEntry re-introduced term-scoped constraint {name} "
                    "(rescopes double-booking to the term -> one-shot-per-term bug)"
                )
        for needle in (
            "def _sync_scope_from_schedule",
            "instruction_shift",
            "term = models.ForeignKey",
        ):
            ok = needle in text
            checks.append({"id": f"scheduling:{needle}", "status": "PASS" if ok else "FAIL"})
            if not ok:
                failures.append(f"scheduling.py missing {needle!r}")

    if not MIGRATION.is_file():
        failures.append("missing migration 0066_scheduleentry_conflict_scope_per_plan.py")
        checks.append({"id": "migration:0066", "status": "FAIL"})
    else:
        mig = MIGRATION.read_text(encoding="utf-8")
        checks.append({"id": "migration:0066", "status": "PASS"})
        for name in REQUIRED_CONSTRAINT_NAMES:
            ok = name in mig
            checks.append({"id": f"migration:{name}", "status": "PASS" if ok else "FAIL"})
            if not ok:
                failures.append(f"migration 0066 missing constraint {name}")

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
        "note": (
            "Per-plan partial unique constraints on discrete TimeSlot; term-wide "
            "names forbidden in the model; gist EXCLUDE deferred."
        ),
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
