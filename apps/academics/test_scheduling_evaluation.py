"""Tests for `scheduling_evaluation` — Schedule quality metrics harness."""

from datetime import time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Subject,
    Term,
)
from apps.academics.scheduling import (
    Room,
    Schedule,
    ScheduleEntry,
    TimeSlot,
)
from apps.academics.scheduling_evaluation import (
    compare_schedules,
    evaluate_schedule,
)

User = get_user_model()


class SchedulingEvaluationTests(TestCase):
    def setUp(self):
        uid = id(self)
        self.creator = User.objects.create_user(
            username=f"se_creator_{uid}",
            email=f"se_creator_{uid}@example.com",
            password="pwd",
        )
        self.t1 = User.objects.create_user(
            username=f"se_t1_{uid}", email=f"t1_{uid}@example.com", password="pwd"
        )
        self.t2 = User.objects.create_user(
            username=f"se_t2_{uid}", email=f"t2_{uid}@example.com", password="pwd"
        )
        self.dept = Department.objects.create(name=f"Dept-{uid}", code=f"D{uid % 10000}")
        self.year = AcademicYear.objects.create(
            name=f"YR-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        self.term = Term.objects.create(
            name=f"T-{uid}",
            academic_year=self.year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        self.classroom_a = Classroom.objects.create(
            name=f"A-{uid}",
            code=f"A{uid % 10000}",
            academic_year=self.year,
            department=self.dept,
        )
        self.classroom_b = Classroom.objects.create(
            name=f"B-{uid}",
            code=f"B{uid % 10000}",
            academic_year=self.year,
            department=self.dept,
        )
        self.subj_math = Subject.objects.create(name=f"Math-{uid}")
        self.subj_eng = Subject.objects.create(name=f"Eng-{uid}")
        self.room1 = Room.objects.create(name=f"R1-{uid}", room_type="CLASSROOM", capacity=30)
        self.room2 = Room.objects.create(name=f"R2-{uid}", room_type="CLASSROOM", capacity=30)
        self.slot_mon_p1 = TimeSlot.objects.create(
            day_of_week=0, start_time=time(9, 0), end_time=time(10, 0), slot_name="P1"
        )
        self.slot_mon_p2 = TimeSlot.objects.create(
            day_of_week=0, start_time=time(10, 0), end_time=time(11, 0), slot_name="P2"
        )
        self.slot_mon_p4 = TimeSlot.objects.create(
            day_of_week=0, start_time=time(13, 0), end_time=time(14, 0), slot_name="P4"
        )
        self.slot_tue_p1 = TimeSlot.objects.create(
            day_of_week=1, start_time=time(9, 0), end_time=time(10, 0), slot_name="P1-Tue"
        )

    def _make_schedule(self):
        return Schedule.objects.create(
            name=f"S-{id(self)}",
            academic_year=self.year,
            term=self.term,
            status="DRAFT",
            created_by=self.creator,
        )

    def test_clean_schedule_reports_zero_violations(self):
        s = self._make_schedule()
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_mon_p1,
        )
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_b, subject=self.subj_eng,
            teacher=self.t2, room=self.room2, time_slot=self.slot_mon_p1,
        )
        metrics = evaluate_schedule(s)
        self.assertEqual(metrics["entry_count"], 2)
        self.assertEqual(metrics["hard_violations_total"], 0)

    def test_teacher_double_booking_cannot_be_stored_at_all(self):
        """Stronger than detecting it: the plan cannot hold one.

        This used to build a teacher double-booking and assert the evaluator
        counted it. The per-plan DB uniques (ScheduleEntry.Meta) now make that
        state unstorable, so the fixture could not be built and the test errored.
        The evaluator's teacher/room counters are kept as defense-in-depth, and
        its classroom counter — the one class with no DB guard — is still
        exercised by test_classroom_double_booking_detected below.
        """
        from django.db import IntegrityError, transaction

        s = self._make_schedule()
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_mon_p1,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ScheduleEntry.objects.create(
                    schedule=s, classroom=self.classroom_b, subject=self.subj_eng,
                    teacher=self.t1, room=self.room2, time_slot=self.slot_mon_p1,
                )

    def test_classroom_double_booking_detected(self):
        s = self._make_schedule()
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_mon_p1,
        )
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_eng,
            teacher=self.t2, room=self.room2, time_slot=self.slot_mon_p1,
        )
        metrics = evaluate_schedule(s)
        self.assertEqual(metrics["hard_violations"]["classroom_double_booked"], 1)

    def test_teacher_gap_period_detected(self):
        # Same teacher: P1 and P4 (non-adjacent) on Monday → 1 gap.
        s = self._make_schedule()
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_mon_p1,
        )
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_b, subject=self.subj_eng,
            teacher=self.t1, room=self.room2, time_slot=self.slot_mon_p4,
        )
        metrics = evaluate_schedule(s)
        self.assertEqual(metrics["teacher_gap_periods_total"], 1)

    def test_back_to_back_no_gap(self):
        s = self._make_schedule()
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_mon_p1,
        )
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_eng,
            teacher=self.t1, room=self.room2, time_slot=self.slot_mon_p2,
        )
        metrics = evaluate_schedule(s)
        self.assertEqual(metrics["teacher_gap_periods_total"], 0)

    def test_subject_spread_across_days(self):
        s = self._make_schedule()
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_mon_p1,
        )
        ScheduleEntry.objects.create(
            schedule=s, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_tue_p1,
        )
        metrics = evaluate_schedule(s)
        # (classroom_a, math) spread across 2 days.
        self.assertEqual(metrics["classroom_spread_avg"], 2.0)

    def test_compare_schedules_prefers_fewer_violations(self):
        """Two rival plans for one term, weighed on hard violations.

        Note this test could not even RUN before the uniques were rescoped to the
        plan (0066): building a second Schedule for the same term collided on the
        term-wide constraint, so the very feature compare_schedules exists for was
        impossible. The rival plans below are the point.

        The 'bad' plan double-books the CLASSROOM rather than the teacher: the
        student group is the one hard-violation class with no DB constraint, so it
        is the only one a stored plan can actually exhibit.
        """
        good = self._make_schedule()
        ScheduleEntry.objects.create(
            schedule=good, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_mon_p1,
        )
        bad = self._make_schedule()
        ScheduleEntry.objects.create(
            schedule=bad, classroom=self.classroom_a, subject=self.subj_math,
            teacher=self.t1, room=self.room1, time_slot=self.slot_mon_p1,
        )
        ScheduleEntry.objects.create(
            schedule=bad, classroom=self.classroom_a, subject=self.subj_eng,
            teacher=self.t2, room=self.room2, time_slot=self.slot_mon_p1,
        )
        result = compare_schedules(good, bad)
        self.assertEqual(result["winner"], "left")
        self.assertIn("hard violations", result["reason"])
