# Timetable Solver — Tenant Admin Guide

**Wave N · v3.95.0 · 2026-05-26**

A greedy slot assigner + conflict detector for school timetables. Handles the 80% case (small school, ~30 classes, ~50 teachers, 30 slots/week); reports conflicts when it can't place a lesson so admins can iterate.

This is **not** a full constraint-satisfaction solver — that's a research project and lands in Wave N+1.

## Data shapes

```python
from apps.academics.timetable_solver import (
    LessonRequest, Resource, TimeSlot, solve, generate_standard_week,
)

slots = generate_standard_week(days=5, periods_per_day=6,
                                start_hour=8, period_minutes=45,
                                break_after_period=3, break_minutes=15)
# → 30 TimeSlots: D1-P1 through D5-P6

teachers = {
    "t-smith": Resource(resource_id="t-smith", kind="teacher",
                        display_name="J. Smith"),
    "t-okafor": Resource(resource_id="t-okafor", kind="teacher",
                          display_name="M. Okafor",
                          availability_slots=("D1-P1", "D2-P3", ...)),  # part-time
}

rooms = {
    "r-101": Resource(resource_id="r-101", kind="room", display_name="Room 101"),
    "lab-1": Resource(resource_id="lab-1", kind="room", display_name="Science Lab"),
}

lessons = [
    LessonRequest(
        lesson_id="math-5a-w",
        class_id="5A",
        subject="Mathematics",
        teacher_id="t-smith",
        weekly_periods=4,
    ),
    LessonRequest(
        lesson_id="chem-5a",
        class_id="5A",
        subject="Chemistry",
        teacher_id="t-okafor",
        required_room_kind="lab",
        preferred_room_ids=("lab-1",),
        weekly_periods=2,
    ),
]

result = solve(lessons, teachers, rooms, list(slots))
# → SolverResult(placed=[...], unplaced=[...], conflicts=[])
```

## Algorithm

1. **Honor locked slots first** — `lesson.locked_slot_ids` reserves a specific (slot, teacher, room) triple.
2. **Sort remaining by (-weekly_periods, lesson_id)** — busiest lessons placed first (most constrained).
3. **For each lesson + each weekly period**, walk slots in order, picking the first that:
   - the teacher is available for (matches `availability_slots`)
   - has at least one matching room available (matches `required_room_kind` + preferred rooms first)
   - doesn't clash with the class's existing placements

Unplaceable lessons are reported with a human-readable reason.

## Conflict detection

`detect_conflicts(placed_list)` scans for:

- `teacher_double_booked` — same teacher, same slot, different lessons
- `room_double_booked` — same room, same slot
- `class_double_booked` — same class, same slot

`solve()` runs this scan automatically and populates `result.conflicts`.

## Room kind matching

A lesson with `required_room_kind="lab"` will only place into rooms whose `resource_id` OR `display_name` contains the substring "lab" (case-insensitive). Same logic for `gym`, `music_room`, etc.

Use `required_room_kind="any"` (default) to accept any room.

## Limitations (Wave N+1)

- **Greedy only** — no backtracking. If the order matters and greedy can't solve, the operator gets an unplaced list.
- **No soft constraints** — "preferred lunch slot for staff," "no double-period gaps for students," etc., are not yet modeled.
- **No optimization** — the solver returns the first valid solution, not the best one.
- **No UI** — the kernel is callable from Python; the operator UI lands in Wave N+1.

## Tests

[apps/academics/tests/test_timetable_solver.py](beta/school-management-system/apps/academics/tests/test_timetable_solver.py) — 15 unit tests covering placement, conflicts, locked slots, room-kind matching, teacher availability.
