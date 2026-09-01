"""The live timetable generator must say what it could not place.

M15 in the 2026-08 audit reported the generator as "a greedy first-fit that
silently skips unplaceable demands". Silently is the whole finding. Reading
``generate_schedule`` before this change:

  * a ``SubjectAssignment`` with no teacher hit ``continue`` and left no trace;
  * a block for which no window worked fell out of ``for window in ...`` with
    nothing recorded;
  * and ``placed_units += 1`` ran either way, so the progress callback reported
    "Placed demand 7 of 7" for a plan that had placed nothing at all.

A DRAFT missing a third of its periods was therefore indistinguishable, in the
plan list and in every progress bar, from a complete one. These tests pin the
report, and the third one pins the mirror: a plan that placed everything must
NOT carry the heading, or the report is noise nobody will read.
"""

from __future__ import annotations

from datetime import time

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Term
from apps.academics.scheduling import (
    UNPLACED_HEADING,
    Room,
    Schedule,
    ScheduleEntry,
    TimeSlot,
    TimetableGenerator,
)
from apps.accounts.models import User


class _Fixture(TestCase):
    """One classroom, one subject, one weekly period. Rooms vary per test."""

    def setUp(self):
        from apps.academics.models import (
            Classroom,
            Department,
            Specialty,
            Subject,
            SubjectAssignment,
        )

        uid = id(self)
        self.user = User.objects.create_user(
            username="unplaced_admin_%s" % uid,
            email="unplaced_admin_%s@example.com" % uid,
            password="password123",
        )
        self.teacher = User.objects.create_user(
            username="unplaced_teacher_%s" % uid,
            email="unplaced_teacher_%s@example.com" % uid,
            password="password123",
        )
        self.year = AcademicYear.objects.create(
            name="2041-2042 %s" % uid,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        self.term = Term.objects.create(
            name="Unplaced Term %s" % uid,
            academic_year=self.year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        self.department = Department.objects.create(
            name="Unplaced Dept %s" % uid, code="UNPL-DEPT-%s" % uid
        )
        self.specialty = Specialty.objects.create(
            department=self.department,
            name="Unplaced Specialty %s" % uid,
            code="UNPL-SPEC-%s" % uid,
        )
        self.classroom = Classroom.objects.create(
            name="Unplaced Class %s" % uid,
            code="UNPL-CLS-%s" % uid,
            academic_year=self.year,
            department=self.department,
        )
        self.subject = Subject.objects.create(name="Unplaced Maths %s" % uid)
        self.slot = TimeSlot.objects.create(
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
            slot_name="Unplaced P1 %s" % uid,
        )
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
        )

    def _generate(self):
        generator = TimetableGenerator(self.year, self.term)
        self.progress = []
        schedule = generator.generate_schedule(
            created_by=self.user,
            on_progress=lambda done, total, message: self.progress.append(message),
        )
        schedule.refresh_from_db()
        return generator, schedule


class ABlockThatFitsNowhereIsReportedTests(_Fixture):
    """No room exists, so every window fails and nothing can be booked."""

    def setUp(self):
        super().setUp()
        self.assignment.teachers.add(self.teacher)

    def test_the_miss_is_recorded_on_the_generator(self):
        generator, _schedule = self._generate()
        self.assertTrue(
            generator.unplaced, "a demand that was placed nowhere left no record"
        )
        self.assertEqual(generator.unplaced[0]["reason"], "no_free_window")

    def test_nothing_was_actually_booked(self):
        """The mirror. Without it the test above could pass on a plan that WORKED."""
        _generator, schedule = self._generate()
        self.assertEqual(
            ScheduleEntry.objects.filter(schedule=schedule).count(),
            0,
            "fixture is wrong: something WAS placed, so there is no miss to report",
        )

    def test_the_plan_itself_carries_the_report(self):
        """A caller that only ever sees the Schedule row must still learn of it."""
        _generator, schedule = self._generate()
        self.assertIn(UNPLACED_HEADING, schedule.notes)
        self.assertIn(str(self.subject), schedule.notes)

    def test_the_progress_line_no_longer_claims_a_placement(self):
        self._generate()
        self.assertTrue(self.progress)
        for message in self.progress:
            self.assertNotIn("Placed demand", message)
        self.assertIn("unplaceable", self.progress[-1])


class ADemandWithNoTeacherIsReportedTests(_Fixture):
    """The other silent exit: `if teacher is None: continue`."""

    def test_the_reason_names_the_missing_teacher(self):
        generator, schedule = self._generate()
        reasons = {miss["reason"] for miss in generator.unplaced}
        self.assertIn("no_teacher", reasons)
        self.assertIn(UNPLACED_HEADING, schedule.notes)


class APlanThatPlacedEverythingSaysNothingTests(_Fixture):
    """Cry-wolf guard: the report must be absent when there is nothing to report."""

    def setUp(self):
        super().setUp()
        self.assignment.teachers.add(self.teacher)
        Room.objects.create(
            name="Unplaced Room %s" % id(self),
            room_type="CLASSROOM",
            capacity=60,
        )

    def test_a_complete_plan_records_no_miss(self):
        generator, schedule = self._generate()
        self.assertEqual(generator.unplaced, [])
        self.assertNotIn(UNPLACED_HEADING, schedule.notes)

    def test_and_it_really_did_place_the_lesson(self):
        _generator, schedule = self._generate()
        self.assertEqual(ScheduleEntry.objects.filter(schedule=schedule).count(), 1)
