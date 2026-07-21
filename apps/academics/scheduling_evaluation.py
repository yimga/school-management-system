"""
Schedule evaluation harness — measures quality of a generated Schedule.

The CP-SAT solver in `scheduling_solver.py` only proves feasibility; it does
not compare two valid schedules. This module evaluates a built Schedule
against four objectives:

    1. hard_violations           — pairs of entries that violate teacher
                                   / classroom / room conflict constraints.
                                   A correct solver should always yield 0.
    2. teacher_gap_periods       — count of empty periods in each teacher's
                                   day between two booked periods. Lower
                                   is better (less idle time).
    3. classroom_spread          — for each (classroom, subject) pair,
                                   how many distinct days the subject is
                                   spread across. Higher is better.
    4. room_utilization          — fraction of (room, slot) cells in use.
                                   Operator-visible capacity signal.

Use as: `evaluate_schedule(schedule)` returns a dict suitable for JSON.
Comparing two schedules: lower hard_violations first, then lower
teacher_gap_periods, then higher classroom_spread.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _entries(schedule) -> list:
    # Cancelled placements are tombstones — exclude from clash / quality metrics
    # so Remove-on-clash actually clears hard violations for the publish gate.
    return list(
        schedule.entries.filter(is_cancelled=False).select_related(
            "teacher", "classroom", "subject", "room", "time_slot"
        )
    )


def _hard_violations(entries: list) -> dict[str, int]:
    by_teacher_slot: dict[tuple, int] = defaultdict(int)
    by_classroom_slot: dict[tuple, int] = defaultdict(int)
    by_room_slot: dict[tuple, int] = defaultdict(int)
    for e in entries:
        # Item 2.3: a slot is only the same occasion within the same week of the
        # rotation. Week A period 1 and week B period 1 are different lessons, so
        # the same teacher in both is not a double booking. ``getattr`` default 1
        # keeps the pure-function contract for the SimpleNamespace stand-ins in
        # test_scheduling_evaluation_unit_loop2 and for pre-2.3 rows.
        slot_id = (e.time_slot_id, getattr(e, "cycle_week", 1) or 1)
        by_teacher_slot[(e.teacher_id, slot_id)] += 1
        by_classroom_slot[(e.classroom_id, slot_id)] += 1
        by_room_slot[(e.room_id, slot_id)] += 1
    return {
        "teacher_double_booked": sum(1 for v in by_teacher_slot.values() if v > 1),
        "classroom_double_booked": sum(1 for v in by_classroom_slot.values() if v > 1),
        "room_double_booked": sum(1 for v in by_room_slot.values() if v > 1),
    }


def _teacher_gap_periods(entries: list) -> dict[int, int]:
    # Group each teacher's bookings by day, then count empty slot-indices
    # between the earliest and latest booked slot of that day.
    by_teacher_day: dict[tuple, list] = defaultdict(list)
    for e in entries:
        slot = e.time_slot
        day = getattr(slot, "day_of_week", None)
        if day is None:
            continue
        by_teacher_day[(e.teacher_id, day)].append(slot)

    gaps: dict[int, int] = defaultdict(int)
    for (teacher_id, _day), slots in by_teacher_day.items():
        if len(slots) < 2:
            continue
        slots_sorted = sorted(slots, key=lambda s: s.start_time)
        # Use slot ordinals over the day for a stable gap count.
        positions = list(range(len(slots_sorted)))
        # The "gap" is the count of distinct start_times between first and last
        # in the same day that have no booking. Simplification: each missing
        # adjacent pair counts as 1.
        for i in range(len(positions) - 1):
            # If the two slots are not back-to-back (start_time of next is more
            # than one period away), count one gap. We approximate "period
            # apart" as: end_time of previous != start_time of next.
            if slots_sorted[i].end_time != slots_sorted[i + 1].start_time:
                gaps[teacher_id] += 1
    return dict(gaps)


def _classroom_spread(entries: list) -> dict[tuple, int]:
    # For each (classroom, subject), how many distinct days is it spread across?
    by_cs: dict[tuple, set] = defaultdict(set)
    for e in entries:
        day = getattr(e.time_slot, "day_of_week", None)
        if day is None:
            continue
        by_cs[(e.classroom_id, e.subject_id)].add(day)
    return {k: len(v) for k, v in by_cs.items()}


def _room_utilization(entries: list, schedule) -> dict[str, Any]:
    # Lazy imports keep this module importable without Django pre-bootstrap.
    from apps.academics.scheduling import Room, TimeSlot

    total_rooms = Room.objects.filter(is_available=True).count()
    total_slots = TimeSlot.objects.filter(is_active=True).count()
    # An n-week rotation has n times as many bookable (room, slot) cells.
    # Every pre-2.3 entry is cycle_week=1, so this is 1 and the ratio is
    # unchanged for a plain weekly timetable.
    cycle_weeks = max(
        [getattr(e, "cycle_week", 1) or 1 for e in entries] or [1]
    )
    capacity = total_rooms * total_slots * cycle_weeks
    booked = len(
        {(e.room_id, e.time_slot_id, getattr(e, "cycle_week", 1) or 1) for e in entries}
    )
    return {
        "booked_cells": booked,
        "capacity_cells": capacity,
        "ratio": (booked / capacity) if capacity else 0.0,
    }


def evaluate_schedule(schedule) -> dict[str, Any]:
    """Compute quality metrics for one Schedule. Pure read; no DB writes."""
    entries = _entries(schedule)
    hard = _hard_violations(entries)
    gap = _teacher_gap_periods(entries)
    spread = _classroom_spread(entries)
    util = _room_utilization(entries, schedule)
    return {
        "schedule_id": schedule.pk,
        "entry_count": len(entries),
        "hard_violations": hard,
        "hard_violations_total": sum(hard.values()),
        "teacher_gap_periods_total": sum(gap.values()),
        "teacher_gap_periods_by_teacher": gap,
        "classroom_spread_by_pair": {
            f"{c}:{s}": v for (c, s), v in spread.items()
        },
        "classroom_spread_avg": (
            sum(spread.values()) / len(spread) if spread else 0.0
        ),
        "room_utilization": util,
    }


def compare_schedules(left, right) -> dict[str, Any]:
    """Lexicographic compare: lower hard, lower gap, higher spread wins."""
    a = evaluate_schedule(left)
    b = evaluate_schedule(right)
    if a["hard_violations_total"] != b["hard_violations_total"]:
        winner = "left" if a["hard_violations_total"] < b["hard_violations_total"] else "right"
        reason = "fewer hard violations"
    elif a["teacher_gap_periods_total"] != b["teacher_gap_periods_total"]:
        winner = "left" if a["teacher_gap_periods_total"] < b["teacher_gap_periods_total"] else "right"
        reason = "fewer teacher gap periods"
    elif a["classroom_spread_avg"] != b["classroom_spread_avg"]:
        winner = "left" if a["classroom_spread_avg"] > b["classroom_spread_avg"] else "right"
        reason = "better subject spread"
    else:
        winner = "tie"
        reason = "indistinguishable on measured objectives"
    return {"winner": winner, "reason": reason, "left": a, "right": b}
