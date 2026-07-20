"""Attendance must land with its tenant FK even when student AND classroom are NULL.

``Attendance.save()`` backfills ``school`` from the student, falling back to the
classroom — but both of those FKs are themselves nullable, and under
schema-per-tenant they are routinely NULL because the schema already isolates the
tenant. When both miss, the backfill was a silent no-op and the row escaped every
``school_id``-filtered consumer (attendance export, multi-campus rollup, tenant
overview) AND survived the offboarding purge as orphan student PII.

Must-FIRE tests: the whole-graph-NULL case is the one that regressed on a real
Buea tenant, where 20/20 roll-call rows landed with school=NULL.
"""
from __future__ import annotations

from datetime import date
from unittest import mock

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
    Specialty,
    Term,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


class AttendanceTenantBackfillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Buea Attendance School",
            slug="buea-attendance-school",
            subdomain="buea-attendance-school",
            country_code="CM",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        Term.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name=Term.Name.FIRST,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(
            school=cls.school, name="General", code="GEN-ATT"
        )
        cls.specialty = Specialty.objects.create(
            school=cls.school, department=dept, name="General", code="GENSPEC-ATT"
        )
        # Classroom school deliberately NULL — the seeded shape.
        cls.classroom = Classroom.objects.create(
            academic_year=cls.year, department=dept, name="Form 1", code="F1-ATT"
        )

    def _student(self, code, *, school):
        return StudentProfile.objects.create(
            school=school,
            first_name="Manyi",
            last_name=code,
            student_code=code,
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )

    def test_backfills_from_student_when_classroom_null(self):
        student = self._student("ATT-1", school=self.school)
        record = Attendance.objects.create(
            student=student, classroom=self.classroom, date=date(2025, 9, 8)
        )
        record.refresh_from_db()
        self.assertEqual(record.school_id, self.school.id)

    def test_backfills_from_connection_when_student_and_classroom_null(self):
        """The regressed case: nothing in the graph carries a school."""
        student = self._student("ATT-2", school=None)
        with mock.patch(
            "apps.schools.rls_context.resolve_connection_school_id",
            return_value=self.school.id,
        ):
            record = Attendance.objects.create(
                student=student, classroom=self.classroom, date=date(2025, 9, 9)
            )
        record.refresh_from_db()
        self.assertEqual(
            record.school_id,
            self.school.id,
            "roll-call row escaped every school_id-scoped consumer",
        )

    def test_explicit_school_is_not_overwritten(self):
        other = School.objects.create(
            name="Other", slug="other-att", subdomain="other-att", is_active=True
        )
        student = self._student("ATT-3", school=self.school)
        record = Attendance.objects.create(
            student=student,
            classroom=self.classroom,
            date=date(2025, 9, 10),
            school=other,
        )
        record.refresh_from_db()
        self.assertEqual(record.school_id, other.id)

    def test_row_still_saves_when_no_school_resolvable(self):
        """RLS/sqlite: no tenant implied — must not raise, just leave NULL."""
        student = self._student("ATT-4", school=None)
        with mock.patch(
            "apps.schools.rls_context.resolve_connection_school_id",
            return_value=None,
        ):
            record = Attendance.objects.create(
                student=student, classroom=self.classroom, date=date(2025, 9, 11)
            )
        record.refresh_from_db()
        self.assertIsNone(record.school_id)
