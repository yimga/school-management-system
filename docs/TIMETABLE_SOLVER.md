# Timetable Solver — Tenant Admin Guide

**Wave N+1 closure · 2026-06-09**

A bounded constraint-satisfaction solver plus deterministic greedy fallback for school timetables. It expands weekly lesson occurrences and enforces locked slots, teacher and room availability, room kinds, and class/teacher/room occupancy.

## Data shapes

```python
from apps.academics.timetable_solver import (
    LessonRequest, Resource, TimeSlot, solve_with_backtracking,
    generate_standard_week,
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

result = solve_with_backtracking(
    lessons=lessons,
    teachers=teachers,
    rooms=rooms,
    slots=slots,
    soft_constraints={"prefer_morning": 0.5},
)
# → SolverResult(..., strategy="csp_backtracking_v1")
```

## Algorithm

1. Expand every lesson into its requested weekly occurrences.
2. Order occurrences by viable candidate count, then stable lesson/occurrence keys.
3. Apply locked slots to their corresponding occurrences.
4. Backtrack over teacher, slot, and matching-room candidates while enforcing occupancy.
5. Order slots by bounded soft weights (`prefer_morning`, `avoid_first_period_for`, `avoid_last_period_for`).
6. If the search limit is reached or the problem is unsatisfiable, return the greedy result with an explicit fallback strategy.

## Conflict detection

`detect_conflicts(placed_list)` scans for:

- `teacher_double_booked` — same teacher, same slot, different lessons
- `room_double_booked` — same room, same slot
- `class_double_booked` — same class, same slot

`solve()` runs this scan automatically and populates `result.conflicts`.

## Room kind matching

A lesson with `required_room_kind="lab"` will only place into rooms whose `resource_id` OR `display_name` contains the substring "lab" (case-insensitive). Same logic for `gym`, `music_room`, etc.

Use `required_room_kind="any"` (default) to accept any room.

## Limitations

- Soft constraints influence slot ordering; this is not a global optimality proof.
- Search is bounded by `max_search_steps` to protect request latency.
- The JSON build surface expects the caller to provide normalized lesson/resource/slot data.

## Tests

[apps/academics/tests/test_timetable_solver.py](../apps/academics/tests/test_timetable_solver.py) — 20 tests covering greedy placement, conflicts, locked slots, availability, weekly occurrence expansion, backtracking, soft ordering, cutoff fallback, and HTTP option validation.
