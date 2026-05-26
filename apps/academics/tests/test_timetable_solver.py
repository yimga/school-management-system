"""Wave N (v3.95.0 — 2026-05-26) — Timetable solver tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.academics.timetable_solver import (
    LessonRequest,
    PlacedLesson,
    Resource,
    SolverResult,
    TimeSlot,
    detect_conflicts,
    generate_standard_week,
    solve,
)


def _t(rid):
    return Resource(resource_id=rid, kind="teacher", display_name=rid)


def _r(rid, name=None):
    return Resource(resource_id=rid, kind="room", display_name=name or rid)


class GenerateWeekTests(SimpleTestCase):

    def test_default_week_30_slots(self):
        slots = generate_standard_week()  # 5 days * 6 periods
        self.assertEqual(len(slots), 30)
        self.assertEqual(slots[0].slot_id, "D1-P1")
        self.assertEqual(slots[-1].slot_id, "D5-P6")

    def test_break_inserted_after_period_3(self):
        slots = generate_standard_week(days=1, periods_per_day=6,
                                        start_hour=8, period_minutes=45,
                                        break_after_period=3, break_minutes=15)
        # P3 ends at 8:00 + 3*45 = 10:15.
        self.assertEqual(slots[2].end_minutes, 8*60 + 3*45)
        # P4 starts at 10:30 (15-min break).
        self.assertEqual(slots[3].start_minutes, 8*60 + 3*45 + 15)


class ConflictDetectionTests(SimpleTestCase):

    def test_no_conflicts_clean_schedule(self):
        placed = [
            PlacedLesson("l1", "D1-P1", "t1", "r1", "c1", "Math"),
            PlacedLesson("l2", "D1-P2", "t1", "r1", "c1", "Math"),
            PlacedLesson("l3", "D1-P1", "t2", "r2", "c2", "English"),
        ]
        self.assertEqual(detect_conflicts(placed), [])

    def test_teacher_double_booked(self):
        placed = [
            PlacedLesson("l1", "D1-P1", "t1", "r1", "c1", "Math"),
            PlacedLesson("l2", "D1-P1", "t1", "r2", "c2", "Sci"),  # same teacher, same slot
        ]
        c = detect_conflicts(placed)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["kind"], "teacher_double_booked")

    def test_room_double_booked(self):
        placed = [
            PlacedLesson("l1", "D1-P1", "t1", "r1", "c1", "Math"),
            PlacedLesson("l2", "D1-P1", "t2", "r1", "c2", "Sci"),
        ]
        c = detect_conflicts(placed)
        self.assertEqual(c[0]["kind"], "room_double_booked")

    def test_class_double_booked(self):
        placed = [
            PlacedLesson("l1", "D1-P1", "t1", "r1", "c1", "Math"),
            PlacedLesson("l2", "D1-P1", "t2", "r2", "c1", "Sci"),
        ]
        c = detect_conflicts(placed)
        self.assertEqual(c[0]["kind"], "class_double_booked")


class GreedySolverTests(SimpleTestCase):

    def test_simple_placement(self):
        slots = list(generate_standard_week(days=2, periods_per_day=3))
        teachers = {"t1": _t("t1")}
        rooms = {"r1": _r("r1")}
        lessons = [LessonRequest(
            lesson_id="math-c1",
            class_id="c1",
            subject="Math",
            teacher_id="t1",
            weekly_periods=3,
        )]
        result = solve(lessons, teachers, rooms, slots)
        self.assertEqual(len(result.placed), 3)
        self.assertEqual(result.unplaced, [])
        self.assertEqual(result.conflicts, [])

    def test_locked_slot_honored(self):
        slots = list(generate_standard_week(days=2, periods_per_day=3))
        teachers = {"t1": _t("t1")}
        rooms = {"r1": _r("r1")}
        lessons = [LessonRequest(
            lesson_id="hist",
            class_id="c1",
            subject="History",
            teacher_id="t1",
            weekly_periods=1,
            locked_slot_ids=("D2-P3",),
        )]
        result = solve(lessons, teachers, rooms, slots)
        # The locked placement should be honored exactly.
        self.assertEqual(len(result.placed), 1)
        self.assertEqual(result.placed[0].slot_id, "D2-P3")

    def test_teacher_conflict_unplaceable(self):
        # Two lessons for the same teacher + class fitting one slot.
        slots = [TimeSlot("D1-P1", 1, 480, 525)]  # only one slot
        teachers = {"t1": _t("t1")}
        rooms = {"r1": _r("r1")}
        lessons = [
            LessonRequest(lesson_id="m", class_id="c1", subject="M",
                          teacher_id="t1", weekly_periods=1),
            LessonRequest(lesson_id="s", class_id="c1", subject="S",
                          teacher_id="t1", weekly_periods=1),
        ]
        result = solve(lessons, teachers, rooms, slots)
        self.assertEqual(len(result.placed), 1)
        self.assertEqual(len(result.unplaced), 1)

    def test_unknown_teacher_reports_unplaced(self):
        slots = list(generate_standard_week(days=1, periods_per_day=2))
        lessons = [LessonRequest(
            lesson_id="x", class_id="c1", subject="X",
            teacher_id="ghost", weekly_periods=1,
        )]
        result = solve(lessons, {}, {"r1": _r("r1")}, slots)
        self.assertEqual(result.placed, [])
        self.assertEqual(len(result.unplaced), 1)
        self.assertIn("ghost", result.unplaced[0]["reason"])

    def test_room_kind_requirement_honored(self):
        slots = list(generate_standard_week(days=1, periods_per_day=2))
        teachers = {"t1": _t("t1")}
        rooms = {"r1": _r("r1", "Classroom"), "lab1": _r("lab1", "Science Lab")}
        # Lesson requires a lab; only lab1 should be picked.
        lessons = [LessonRequest(
            lesson_id="chem",
            class_id="c1",
            subject="Chemistry",
            teacher_id="t1",
            required_room_kind="lab",
            weekly_periods=1,
        )]
        result = solve(lessons, teachers, rooms, slots)
        self.assertEqual(len(result.placed), 1)
        self.assertEqual(result.placed[0].room_id, "lab1")

    def test_preferred_room_wins_over_default(self):
        slots = list(generate_standard_week(days=1, periods_per_day=1))
        teachers = {"t1": _t("t1")}
        rooms = {"r1": _r("r1"), "r2": _r("r2")}
        lessons = [LessonRequest(
            lesson_id="m",
            class_id="c1",
            subject="Math",
            teacher_id="t1",
            preferred_room_ids=("r2",),
            weekly_periods=1,
        )]
        result = solve(lessons, teachers, rooms, slots)
        self.assertEqual(result.placed[0].room_id, "r2")

    def test_teacher_availability_constraint(self):
        slots = list(generate_standard_week(days=1, periods_per_day=2))
        teachers = {"t1": Resource(
            resource_id="t1", kind="teacher", display_name="t1",
            availability_slots=("D1-P2",),  # only available P2
        )}
        rooms = {"r1": _r("r1")}
        lessons = [LessonRequest(
            lesson_id="m", class_id="c1", subject="M",
            teacher_id="t1", weekly_periods=1,
        )]
        result = solve(lessons, teachers, rooms, slots)
        self.assertEqual(len(result.placed), 1)
        self.assertEqual(result.placed[0].slot_id, "D1-P2")

    def test_class_double_booking_prevented(self):
        # Same class wants two lessons at any of the 2 available slots.
        slots = list(generate_standard_week(days=1, periods_per_day=2))
        teachers = {"t1": _t("t1"), "t2": _t("t2")}
        rooms = {"r1": _r("r1"), "r2": _r("r2")}
        lessons = [
            LessonRequest(lesson_id="m", class_id="c1", subject="M",
                          teacher_id="t1", weekly_periods=1),
            LessonRequest(lesson_id="e", class_id="c1", subject="E",
                          teacher_id="t2", weekly_periods=1),
        ]
        result = solve(lessons, teachers, rooms, slots)
        # Both placed in different slots, no conflicts.
        self.assertEqual(len(result.placed), 2)
        slot_ids = {p.slot_id for p in result.placed}
        self.assertEqual(len(slot_ids), 2)
        self.assertEqual(result.conflicts, [])

    def test_locked_slot_unknown_reports_unplaced(self):
        slots = list(generate_standard_week(days=1, periods_per_day=2))
        teachers = {"t1": _t("t1")}
        rooms = {"r1": _r("r1")}
        lessons = [LessonRequest(
            lesson_id="x", class_id="c1", subject="X",
            teacher_id="t1", weekly_periods=1,
            locked_slot_ids=("D99-P99",),
        )]
        result = solve(lessons, teachers, rooms, slots)
        # Locked slot doesn't exist -> reported unplaced for the locked attempt.
        unplaced_reasons = " ".join(u["reason"] for u in result.unplaced)
        self.assertIn("locked slot", unplaced_reasons)
