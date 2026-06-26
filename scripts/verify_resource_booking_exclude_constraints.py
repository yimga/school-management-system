#!/usr/bin/env python3
"""Resource booking Postgres gist exclusion verifier (W6 / metric 10)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODELS = REPO / "apps" / "schoolops" / "models_resource_booking.py"
SERVICES = REPO / "apps" / "schoolops" / "booking_services.py"
MIGRATION = REPO / "apps" / "schoolops" / "migrations" / "0029_resource_booking_exclude_constraint.py"
TEST = REPO / "apps" / "schoolops" / "tests" / "test_resource_booking.py"
OUT = REPO / "docs" / "generated" / "resource_booking_exclude_constraints_audit.json"

REQUIRED = (
    ("model:ExclusionConstraint", "exclude_overlapping_resource_bookings", MODELS),
    ("model:DateTimeRangeField", "time_range", MODELS),
    ("service:create_resource_booking", "def create_resource_booking", SERVICES),
    ("service:BookingConflictError", "class BookingConflictError", SERVICES),
    ("migration:btree_gist", "BtreeGistExtension", MIGRATION),
    (
        "migration:exclude_constraint",
        "exclude_overlapping_resource_bookings",
        MIGRATION,
    ),
    ("test:postgres_exclusion", "ResourceBookingPostgresExclusionTests", TEST),
    ("test:capacity", "test_fractional_capacity_allows_two_when_capacity_two", TEST),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resource booking exclusion gate")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    checks: list[dict[str, str]] = []

    for check_id, needle, path in REQUIRED:
        ok = path.is_file() and needle in path.read_text(encoding="utf-8")
        checks.append({"id": check_id, "status": "PASS" if ok else "FAIL"})
        if not ok:
            failures.append(f"{check_id}: missing {needle!r} in {path.relative_to(REPO)}")

    verdict = (
        "RESOURCE_BOOKING_EXCLUDE_CONSTRAINTS_PASS"
        if not failures
        else "RESOURCE_BOOKING_EXCLUDE_CONSTRAINTS_FAIL"
    )
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
        print(f"verify_resource_booking_exclude_constraints: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_resource_booking_exclude_constraints: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
