"""Item 2.4 — Room and TimeSlot are tenant-scoped.

MUST-FIRE. Restore ``Room.name = models.CharField(..., unique=True)`` or
``TimeSlot.unique_together = ("day_of_week", "start_time", "end_time")`` and
``TwoSchoolsSamePeriodAndRoomTests`` raises IntegrityError instead of passing.

Why this mattered even though production runs schema-per-tenant: the platform
also ships an RLS / shared-table mode (``TENANCY_MODE=RLS``,
``USE_DJANGO_TENANTS=0``) in which every school lives in ONE set of tables, and
the test suite itself runs in exactly that mode. Under it, the old global
uniques meant the second school on the instance could not create a room called
"Lab 1" or a period at 08:00.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.academics.scheduling import Room, TimeSlot, TimetableGenerator
from apps.accounts.models import User
from apps.schools.models import School


def _school(tag):
    uid = uuid.uuid4().hex[:8]
    return School.objects.create(
        name=f"{tag} {uid}",
        slug=f"{tag.lower()}-{uid}",
        subdomain=f"{tag.lower()}-{uid}",
        is_active=True,
    )


class TwoSchoolsSamePeriodAndRoomTests(TestCase):
    """Acceptance 3 — same period label and same room name, no collision."""

    def setUp(self):
        self.alpha = _school("Alpha")
        self.beta = _school("Beta")

    def test_two_schools_define_the_same_room_name(self):
        a = Room.objects.create(
            school=self.alpha, name="Lab 1", room_type="LAB", capacity=30
        )
        b = Room.objects.create(
            school=self.beta, name="Lab 1", room_type="LAB", capacity=30
        )
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual(
            Room.objects.filter(name="Lab 1").count(),
            2,
            "two tenants must each be able to own a room called 'Lab 1'",
        )

    def test_two_schools_define_the_same_period(self):
        a = TimeSlot.objects.create(
            school=self.alpha,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            slot_name="Period 1",
            is_active=True,
        )
        b = TimeSlot.objects.create(
            school=self.beta,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            slot_name="Period 1",
            is_active=True,
        )
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual(
            TimeSlot.objects.filter(slot_name="Period 1", start_time=time(8, 0)).count(),
            2,
        )

    def test_one_school_still_cannot_duplicate_its_own_room_name(self):
        """Per-school uniqueness is real, not merely dropped."""
        Room.objects.create(
            school=self.alpha, name="Lab 1", room_type="LAB", capacity=30
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Room.objects.create(
                    school=self.alpha, name="Lab 1", room_type="LAB", capacity=25
                )

    def test_one_school_still_cannot_duplicate_its_own_period(self):
        TimeSlot.objects.create(
            school=self.alpha,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            slot_name="Period 1",
            is_active=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TimeSlot.objects.create(
                    school=self.alpha,
                    day_of_week=0,
                    start_time=time(8, 0),
                    end_time=time(9, 0),
                    slot_name="Registration",
                    is_active=True,
                )


class GeneratorResourceScopingTests(TestCase):
    """The generator books its OWN rooms/periods, plus unattributed legacy rows."""

    def _graph(self, school, tag):
        uid = uuid.uuid4().hex[:8]
        year = AcademicYear.objects.create(
            school=school,
            name=f"2025/2026-{tag}-{uid}",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(
            school=school, name=f"Dept-{tag}-{uid}", code=f"D{uid}"
        )
        specialty = Specialty.objects.create(
            school=school, department=dept, name="General", code=f"SP{uid}"
        )
        classroom = Classroom.objects.create(
            school=school,
            academic_year=year,
            department=dept,
            name="Form 1",
            code=f"F1-{uid}",
        )
        subject = Subject.objects.create(school=school, name=f"Math-{uid}")
        teacher = User.objects.create_user(
            username=f"t_{tag}_{uid}", password="Test1234", role=User.Role.TEACHER
        )
        assignment = SubjectAssignment.objects.create(
            school=school,
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
        )
        assignment.teachers.add(teacher)
        admin = User.objects.create_user(
            username=f"a_{tag}_{uid}", password="Test1234", role=User.Role.ADMIN
        )
        return {"year": year, "term": term, "admin": admin}

    def test_generator_never_books_another_schools_room(self):
        alpha, beta = _school("Alpha"), _school("Beta")
        alpha_graph = self._graph(alpha, "alpha")

        alpha_room = Room.objects.create(
            school=alpha, name="Lab 1", room_type="LAB", capacity=40
        )
        Room.objects.create(school=beta, name="Lab 1", room_type="LAB", capacity=40)
        TimeSlot.objects.create(
            school=alpha,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            slot_name="Period 1",
            is_active=True,
        )
        beta_slot = TimeSlot.objects.create(
            school=beta,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            slot_name="Period 1",
            is_active=True,
        )

        schedule = TimetableGenerator(
            alpha_graph["year"], alpha_graph["term"]
        ).generate_schedule(created_by=alpha_graph["admin"])

        entries = list(schedule.entries.all())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].room_id, alpha_room.pk)
        self.assertNotEqual(entries[0].time_slot_id, beta_slot.pk)

    def test_unattributed_legacy_rows_stay_usable_by_everyone(self):
        """school=NULL is the pre-2.4 shared pool; the backfill leaves it alone.

        This is what makes the migration non-destructive: a row nobody could be
        proven to own keeps working for every tenant instead of being handed to
        one of them.
        """
        alpha = _school("Alpha")
        graph = self._graph(alpha, "legacy")
        legacy_room = Room.objects.create(
            school=None, name="Shared Hall", room_type="AUDITORIUM", capacity=200
        )
        legacy_slot = TimeSlot.objects.create(
            school=None,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            slot_name="Period 1",
            is_active=True,
        )

        schedule = TimetableGenerator(
            graph["year"], graph["term"]
        ).generate_schedule(created_by=graph["admin"])

        entries = list(schedule.entries.all())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].room_id, legacy_room.pk)
        self.assertEqual(entries[0].time_slot_id, legacy_slot.pk)


class BackfillAttributionTests(TestCase):
    """The 0071 rules, exercised against the live schema.

    The migration itself cannot be re-run inside a TestCase, so its two
    decisions are asserted here as the invariants they encode.
    """

    def test_global_uniqueness_could_never_collide_after_partitioning(self):
        # Rule stated in 0071's docstring: any row set that satisfied the OLD
        # global unique still satisfies the per-school unique. Two rooms that
        # differ globally by name cannot collide when both are given to one
        # school, because the per-school key includes that same name.
        alpha = _school("Alpha")
        Room.objects.create(school=alpha, name="R1", room_type="LAB", capacity=10)
        Room.objects.create(school=alpha, name="R2", room_type="LAB", capacity=10)
        self.assertEqual(Room.objects.filter(school=alpha).count(), 2)

    def test_null_school_rows_are_not_deduplicated(self):
        # Deliberate: SQL NULL != NULL, so unattributed legacy rows are not
        # retro-constrained by the new per-school unique.
        Room.objects.create(school=None, name="Legacy", room_type="LAB", capacity=10)
        Room.objects.create(school=None, name="Legacy", room_type="LAB", capacity=10)
        self.assertEqual(Room.objects.filter(school__isnull=True).count(), 2)
