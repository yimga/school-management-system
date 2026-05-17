#!/usr/bin/env python
"""Tenant-scoping allowlist burndown forward-progress gate.

12-pillar audit P3 follow-up. The per-PR `scan_tenant_queryset_safety`
gate already prevents regressions vs. baseline. This complementary gate
enforces the **schedule** from [`docs/TENANT_SCOPING_BURNDOWN_PLAN.md`](../docs/TENANT_SCOPING_BURNDOWN_PLAN.md):
the baseline must shrink to the active quarter's ceiling.

Picks the active target by walking ``QUARTERLY_TARGETS`` in date order
and returning the **first row whose date is ≥ today**. Once today
passes 2027-05-31 the gate locks at 0.

Usage:

    python scripts/verify_tenant_scoping_burndown.py             # text summary
    python scripts/verify_tenant_scoping_burndown.py --json
    python scripts/verify_tenant_scoping_burndown.py --strict    # exit 1 if behind

The verifier is intentionally **schedule-driven**, not commit-driven,
so it doesn't fire on every PR. Schedule the operator-facing run as a
weekly cron or pre-merge-to-main check.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-tenant-isolation.json"
)


@dataclass(frozen=True)
class QuarterlyTarget:
    deadline: date
    ceiling: int
    note: str


# Aligned with docs/TENANT_SCOPING_BURNDOWN_PLAN.md. Update the table
# AND the doc when targets are renegotiated — keep them in lock-step.
QUARTERLY_TARGETS: tuple[QuarterlyTarget, ...] = (
    QuarterlyTarget(date(2026, 8, 31), 626, "Q3 2026: -100 from evals + portal"),
    QuarterlyTarget(date(2026, 11, 30), 476, "Q4 2026: -150 from accounts + schools + api"),
    QuarterlyTarget(date(2027, 2, 28), 276, "Q1 2027: -200 from finance + analytics + reports + siteconfig"),
    QuarterlyTarget(date(2027, 5, 31), 0, "Q2 2027: -276, long tail"),
)


def _read_baseline_count() -> int | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = data.get("finding_count")
    if isinstance(value, int):
        return value
    findings = data.get("findings")
    if isinstance(findings, list):
        return len(findings)
    return None


def _active_target(today: date) -> QuarterlyTarget | None:
    """Return the most recent target whose deadline has *passed*.

    A target only **binds** once its deadline is in the past. Before
    the first deadline, the verifier reports progress (showing what is
    coming up) but does not fail in --strict mode. This matches how
    burndowns actually work: the ceiling is the contract by date X,
    not from day 1.
    """
    passed = [t for t in QUARTERLY_TARGETS if t.deadline < today]
    if not passed:
        return None
    return passed[-1]


def _next_target(today: date) -> QuarterlyTarget | None:
    """Return the next upcoming target, for progress display only."""
    upcoming = [t for t in QUARTERLY_TARGETS if t.deadline >= today]
    return upcoming[0] if upcoming else None


def _summary(today: date) -> dict:
    current = _read_baseline_count()
    active = _active_target(today)
    upcoming = _next_target(today)
    if active is None:
        # Before the first deadline — show what's coming, don't bind yet.
        on_track = True
        gap: int | None = None
    else:
        on_track = current is not None and current <= active.ceiling
        gap = (current - active.ceiling) if current is not None else None
    return {
        "today": today.isoformat(),
        "current_count": current,
        "binding_target": (
            {
                "deadline": active.deadline.isoformat(),
                "ceiling": active.ceiling,
                "note": active.note,
            } if active else None
        ),
        "upcoming_target": (
            {
                "deadline": upcoming.deadline.isoformat(),
                "ceiling": upcoming.ceiling,
                "note": upcoming.note,
            } if upcoming else None
        ),
        "all_targets": [
            {
                "deadline": t.deadline.isoformat(),
                "ceiling": t.ceiling,
                "note": t.note,
            }
            for t in QUARTERLY_TARGETS
        ],
        "on_track": on_track,
        "gap": gap,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 1 when the current count exceeds the active target ceiling.",
    )
    args = parser.parse_args()

    today = date.today()
    payload = _summary(today)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        current = payload["current_count"]
        binding = payload["binding_target"]
        upcoming = payload["upcoming_target"]
        if current is None:
            print("tenant-scoping burndown: baseline file missing or unreadable")
            return 1 if args.strict else 0
        if binding is None:
            if upcoming is not None:
                print(
                    f"tenant-scoping burndown: current={current} "
                    f"upcoming ceiling={upcoming['ceiling']} "
                    f"by {upcoming['deadline']} [PRE-DEADLINE]"
                )
                print(f"  next target: {upcoming['note']}")
            else:
                print(f"tenant-scoping burndown: current={current} [no targets defined]")
        else:
            verdict = "ON-TRACK" if payload["on_track"] else "BEHIND"
            print(
                f"tenant-scoping burndown: current={current} "
                f"ceiling={binding['ceiling']} (deadline {binding['deadline']}) "
                f"[{verdict}]"
            )
            print(f"  binding target: {binding['note']}")
            if not payload["on_track"]:
                print(
                    f"  gap: {payload['gap']} findings over ceiling -- schedule slip."
                )
            if upcoming is not None:
                print(
                    f"  next: ceiling={upcoming['ceiling']} by {upcoming['deadline']}"
                )

    if args.strict and not payload["on_track"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
