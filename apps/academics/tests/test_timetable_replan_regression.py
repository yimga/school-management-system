"""A term's timetable must be re-plannable. Phase 4E made it a one-shot.

Found by an A-Z audit follow-up (2026-07-16) while triaging 4 "broken" scheduling
tests. They were not broken -- they were the canary, and they were right.

``0055_scheduleentry_db_conflict_constraints`` (Phase 4E) added DB partial
uniques to stop teacher/room double-booking. The intent is correct and worth
keeping. The SCOPE is not: the constraints key on ``term``, but bookings live in
a ``Schedule``, and a term can hold many Schedules --

  * ``TimetableGenerator.generate`` (scheduling.py) creates a NEW DRAFT Schedule
    on every run and never removes the previous one;
  * ``solve_timetable`` (scheduling_solver.py) does the same;
  * ``Schedule`` has DRAFT/PUBLISHED statuses and NO one-per-term constraint;
  * ``compare_schedules`` exists precisely to weigh two candidate Schedules for
    one term against each other.

So the second generation for a term collides with the first on
(term, teacher, time_slot) and dies with IntegrityError. A school could generate
its timetable exactly once, ever, and never re-plan it. The generator's OWN
in-run guard is ``schedule=schedule``-scoped, which is the scope the DB should
have used too.

These tests pin the behaviour the product needs: no double-booking WITHIN a plan,
while a term may still hold several plans.
"""

from __future__ import annotations

from datetime import time

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Term
from apps.academics.scheduling import Room, Schedule, ScheduleEntry, TimeSlot
from apps.accounts.models import User


class _SchedulingFixture(TestCase):
    def setUp(self):
        from apps.academics.models import Classroom, Department, Subject

        uid = id(self)
        self.user = User.objects.create_user(
            username="replan_admin_%s" % uid,
            email="replan_admin_%s@example.com" % uid,
            password="password123",
        )
        self.teacher = User.objects.create_user(
            username="replan_teacher_%s" % uid,
            email="replan_teacher_%s@example.com" % uid,
            password="password123",
        )
        self.year = AcademicYear.objects.create(
            name="2031-2032",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        self.term = Term.objects.create(
            name="Replan Term",
            academic_year=self.year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        self.department = Department.objects.create(
            name="Replan Dept", code="REPLAN-DEPT-%s" % uid
        )
        self.classroom = Classroom.objects.create(
            name="Replan Class",
            code="REPLAN-CLS-%s" % uid,
            academic_year=self.year,
            department=self.department,
        )
        self.subject = Subject.objects.create(name="Replan Maths %s" % uid)
        self.room = Room.objects.create(
            name="Replan Room %s" % uid, room_type="CLASSROOM", capacity=30
        )
        self.slot = TimeSlot.objects.create(
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
            slot_name="Replan P1 %s" % uid,
        )

    def _schedule(self, name: str, status: str = "DRAFT") -> Schedule:
        return Schedule.objects.create(
            name=name,
            academic_year=self.year,
            term=self.term,
            status=status,
            created_by=self.user,
        )

    def _entry(self, schedule: Schedule) -> ScheduleEntry:
        return ScheduleEntry.objects.create(
            schedule=schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )


class TermMayHoldSeveralPlansTests(_SchedulingFixture):
    """The regression: a term must be re-plannable."""

    def test_a_second_draft_for_the_same_term_can_be_built(self):
        first = self._schedule("First draft")
        self._entry(first)

        second = self._schedule("Second draft")
        self._entry(second)  # must NOT raise IntegrityError

        self.assertEqual(
            ScheduleEntry.objects.filter(term=self.term).count(),
            2,
            "a term must be able to hold two candidate plans -- otherwise a "
            "school can generate its timetable exactly once, ever",
        )

    def test_a_replacement_draft_can_be_built_beside_a_published_plan(self):
        published = self._schedule("Published plan", status="PUBLISHED")
        self._entry(published)

        replacement = self._schedule("Replacement draft")
        self._entry(replacement)

        self.assertEqual(ScheduleEntry.objects.filter(term=self.term).count(), 2)

    def test_two_candidate_plans_can_be_compared(self):
        """compare_schedules exists for exactly this and could never run."""
        from apps.academics.scheduling_evaluation import compare_schedules

        good = self._schedule("Good")
        self._entry(good)
        bad = self._schedule("Bad")
        self._entry(bad)

        result = compare_schedules(good, bad)
        self.assertIn("winner", result)


class NoDoubleBookingWithinOnePlanTests(_SchedulingFixture):
    """Phase 4E's real intent must survive the rescope."""

    def test_same_teacher_twice_in_one_plan_is_rejected(self):
        from django.db import IntegrityError

        schedule = self._schedule("Plan")
        self._entry(schedule)
        with self.assertRaises(
            IntegrityError,
            msg="a teacher must not be double-booked inside one plan",
        ):
            self._entry(schedule)

    def test_same_room_twice_in_one_plan_is_rejected(self):
        from django.db import IntegrityError

        from apps.academics.models import Classroom, Subject

        schedule = self._schedule("Plan")
        self._entry(schedule)
        other_teacher = User.objects.create_user(
            username="replan_teacher2_%s" % id(self),
            email="replan_teacher2_%s@example.com" % id(self),
            password="password123",
        )
        other_class = Classroom.objects.create(
            name="Replan Class B",
            code="REPLAN-CLS-B-%s" % id(self),
            academic_year=self.year,
            department=self.department,
        )
        other_subject = Subject.objects.create(name="Replan Eng %s" % id(self))
        with self.assertRaises(
            IntegrityError,
            msg="a room must not be double-booked inside one plan",
        ):
            ScheduleEntry.objects.create(
                schedule=schedule,
                classroom=other_class,
                subject=other_subject,
                teacher=other_teacher,
                room=self.room,
                time_slot=self.slot,
            )

    def test_a_cancelled_entry_frees_its_slot(self):
        schedule = self._schedule("Plan")
        first = self._entry(schedule)
        ScheduleEntry.objects.filter(pk=first.pk).update(is_cancelled=True)
        self._entry(schedule)  # the slot is free again
        self.assertEqual(
            ScheduleEntry.objects.filter(schedule=schedule, is_cancelled=False).count(),
            1,
        )

    def test_clean_still_rejects_a_duplicate_before_the_db_does(self):
        from django.core.exceptions import ValidationError

        schedule = self._schedule("Plan")
        self._entry(schedule)
        dup = ScheduleEntry(
            schedule=schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        with self.assertRaises(ValidationError):
            dup.clean()

    def test_clean_permits_the_same_booking_in_a_different_plan(self):
        schedule = self._schedule("Plan")
        self._entry(schedule)
        other = self._schedule("Other plan")
        candidate = ScheduleEntry(
            schedule=other,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        candidate.clean()  # must not raise -- a rival plan is not a conflict


class GeneratorCanRegenerateTests(_SchedulingFixture):
    """End-to-end: the real generator, run twice, as a school would."""

    def test_generate_twice_for_one_term(self):
        from apps.academics.models import Specialty, SubjectAssignment
        from apps.academics.scheduling import TimetableGenerator

        specialty = Specialty.objects.create(
            school=None,
            department=self.department,
            name="Replan Spec",
            code="REPLAN-SPEC-%s" % id(self),
        )
        assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=specialty,
            subject=self.subject,
        )
        assignment.teachers.add(self.teacher)

        generator = TimetableGenerator(self.year, self.term)
        first = generator.generate_schedule(created_by=self.user)
        self.assertIsNotNone(first)

        # A school re-planning its term. This died with IntegrityError.
        second = TimetableGenerator(self.year, self.term).generate_schedule(
            created_by=self.user
        )
        self.assertIsNotNone(second)
        self.assertNotEqual(first.pk, second.pk)
