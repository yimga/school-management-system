"""No-DB unit coverage for the pure helpers in
`apps.academics.scheduling_evaluation` (Testing #16, loop 2).

The existing ``test_scheduling_evaluation.py`` is a DB-backed ``TestCase`` that
drives ``evaluate_schedule`` / ``compare_schedules`` end to end. The three
private metric functions — ``_hard_violations``, ``_teacher_gap_periods`` and
``_classroom_spread`` — are pure: they take a plain list of entry objects and
read only ``*_id`` attributes and a duck-typed ``time_slot``. They are exercised
here in isolation with ``SimpleNamespace`` stand-ins, so no database is required.

Brand-new file; no edits to existing tests or source.
"""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.academics.scheduling_evaluation import (
    _classroom_spread,
    _hard_violations,
    _teacher_gap_periods,
)


def _slot(*, slot_id, day, start, end):
    return SimpleNamespace(
        # _hard_violations reads e.time_slot_id; the others read e.time_slot.
        id=slot_id,
        day_of_week=day,
        start_time=start,
        end_time=end,
    )


def _entry(*, teacher=1, classroom=1, room=1, subject=1, slot):
    return SimpleNamespace(
        teacher_id=teacher,
        classroom_id=classroom,
        room_id=room,
        subject_id=subject,
        time_slot_id=slot.id,
        time_slot=slot,
    )


class HardViolationsTests(SimpleTestCase):
    def test_no_entries_is_all_zero(self):
        result = _hard_violations([])
        self.assertEqual(
            result,
            {
                "teacher_double_booked": 0,
                "classroom_double_booked": 0,
                "room_double_booked": 0,
            },
        )

    def test_teacher_double_booked_in_same_slot(self):
        slot = _slot(slot_id=10, day=0, start=time(8), end=time(9))
        # Same teacher, same slot, different room/classroom -> teacher clash.
        entries = [
            _entry(teacher=7, classroom=1, room=1, slot=slot),
            _entry(teacher=7, classroom=2, room=2, slot=slot),
        ]
        result = _hard_violations(entries)
        self.assertEqual(result["teacher_double_booked"], 1)
        self.assertEqual(result["classroom_double_booked"], 0)
        self.assertEqual(result["room_double_booked"], 0)

    def test_room_and_classroom_double_booked(self):
        slot = _slot(slot_id=11, day=0, start=time(8), end=time(9))
        entries = [
            _entry(teacher=1, classroom=5, room=9, slot=slot),
            _entry(teacher=2, classroom=5, room=9, slot=slot),
        ]
        result = _hard_violations(entries)
        self.assertEqual(result["classroom_double_booked"], 1)
        self.assertEqual(result["room_double_booked"], 1)
        self.assertEqual(result["teacher_double_booked"], 0)

    def test_distinct_slots_no_violation(self):
        s1 = _slot(slot_id=1, day=0, start=time(8), end=time(9))
        s2 = _slot(slot_id=2, day=0, start=time(9), end=time(10))
        entries = [
            _entry(teacher=3, classroom=3, room=3, slot=s1),
            _entry(teacher=3, classroom=3, room=3, slot=s2),
        ]
        self.assertEqual(sum(_hard_violations(entries).values()), 0)


class TeacherGapPeriodsTests(SimpleTestCase):
    def test_single_booking_has_no_gap(self):
        slot = _slot(slot_id=1, day=1, start=time(8), end=time(9))
        self.assertEqual(_teacher_gap_periods([_entry(teacher=4, slot=slot)]), {})

    def test_back_to_back_slots_have_no_gap(self):
        # end_time of first == start_time of second -> contiguous.
        s1 = _slot(slot_id=1, day=2, start=time(8), end=time(9))
        s2 = _slot(slot_id=2, day=2, start=time(9), end=time(10))
        entries = [_entry(teacher=4, slot=s1), _entry(teacher=4, slot=s2)]
        self.assertEqual(_teacher_gap_periods(entries), {})

    def test_non_contiguous_slots_count_one_gap(self):
        # 8-9 then 10-11: end(9) != start(10) -> one gap.
        s1 = _slot(slot_id=1, day=2, start=time(8), end=time(9))
        s2 = _slot(slot_id=2, day=2, start=time(10), end=time(11))
        entries = [_entry(teacher=4, slot=s1), _entry(teacher=4, slot=s2)]
        self.assertEqual(_teacher_gap_periods(entries), {4: 1})

    def test_gaps_are_per_teacher_and_per_day(self):
        # Teacher 4 has a gap on Monday(day=0); the two slots on Tuesday are
        # contiguous, so only one gap is recorded.
        mon1 = _slot(slot_id=1, day=0, start=time(8), end=time(9))
        mon2 = _slot(slot_id=2, day=0, start=time(11), end=time(12))
        tue1 = _slot(slot_id=3, day=1, start=time(8), end=time(9))
        tue2 = _slot(slot_id=4, day=1, start=time(9), end=time(10))
        entries = [
            _entry(teacher=4, slot=mon1),
            _entry(teacher=4, slot=mon2),
            _entry(teacher=4, slot=tue1),
            _entry(teacher=4, slot=tue2),
        ]
        self.assertEqual(_teacher_gap_periods(entries), {4: 1})

    def test_slot_without_day_is_ignored(self):
        no_day = SimpleNamespace(
            id=1, day_of_week=None, start_time=time(8), end_time=time(9)
        )
        with_day = _slot(slot_id=2, day=0, start=time(10), end=time(11))
        entries = [
            _entry(teacher=4, slot=no_day),
            _entry(teacher=4, slot=with_day),
        ]
        # Only one usable slot for the teacher's day -> no gaps.
        self.assertEqual(_teacher_gap_periods(entries), {})


class ClassroomSpreadTests(SimpleTestCase):
    def test_same_subject_across_two_days(self):
        d1 = _slot(slot_id=1, day=0, start=time(8), end=time(9))
        d2 = _slot(slot_id=2, day=2, start=time(8), end=time(9))
        entries = [
            _entry(classroom=5, subject=8, slot=d1),
            _entry(classroom=5, subject=8, slot=d2),
        ]
        self.assertEqual(_classroom_spread(entries), {(5, 8): 2})

    def test_same_day_repeats_count_once(self):
        d1 = _slot(slot_id=1, day=0, start=time(8), end=time(9))
        d1b = _slot(slot_id=2, day=0, start=time(10), end=time(11))
        entries = [
            _entry(classroom=5, subject=8, slot=d1),
            _entry(classroom=5, subject=8, slot=d1b),
        ]
        # Distinct DAYS, not distinct slots -> spread of 1.
        self.assertEqual(_classroom_spread(entries), {(5, 8): 1})

    def test_distinct_pairs_tracked_separately(self):
        d1 = _slot(slot_id=1, day=0, start=time(8), end=time(9))
        entries = [
            _entry(classroom=5, subject=8, slot=d1),
            _entry(classroom=6, subject=8, slot=d1),
        ]
        self.assertEqual(_classroom_spread(entries), {(5, 8): 1, (6, 8): 1})

    def test_slot_without_day_ignored(self):
        no_day = SimpleNamespace(
            id=1, day_of_week=None, start_time=time(8), end_time=time(9)
        )
        self.assertEqual(_classroom_spread([_entry(slot=no_day)]), {})
