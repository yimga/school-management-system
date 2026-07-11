"""Attendance.school must never persist NULL.

The teacher roll-call web UI, mobile offline sync, and the REST `record` action
all create attendance via update_or_create WITHOUT passing school. A school=NULL
row is silently dropped by every school-scoped consumer (CSV export, multi-campus
rollup, tenant-overview viz, student-transfer export) and — worse — survives the
tenant offboarding purge (which deletes by school_id) as orphan student PII. The
model-level save() chokepoint backfills school from the student so no create path
can leave it NULL.
"""

from __future__ import annotations

from datetime import date

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


class AttendanceSchoolBackfillTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Attend Test",
            slug="attend-test",
            subdomain="attend-test",
            country_code="FR",
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-att",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
            school=self.school,
        )
        self.term = Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=self.year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(
            name="Science", code="SCI", school=self.school
        )
        self.specialty = Specialty.objects.create(
            name="General", code="GEN", department=self.department
        )
        self.classroom = Classroom.objects.create(
            name="Form 1",
            code="F1",
            academic_year=self.year,
            department=self.department,
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            student_code="STD001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            school=self.school,
        )

    def test_rollcall_path_backfills_school(self):
        # Mirrors portal.take_student_attendance: student= + classroom= loaded,
        # defaults carry only status.
        att, _ = Attendance.objects.update_or_create(
            student=self.student,
            classroom=self.classroom,
            date=date(2025, 9, 10),
            defaults={"status": "present"},
        )
        att.refresh_from_db()
        self.assertEqual(att.school_id, self.school.id)

    def test_rest_record_path_backfills_school(self):
        # Mirrors academics.api_views record + mobile sync: student_id (unloaded).
        Attendance.objects.update_or_create(
            student_id=self.student.id,
            classroom=self.classroom,
            date=date(2025, 9, 11),
            defaults={"status": "late"},
        )
        att = Attendance.objects.get(student=self.student, date=date(2025, 9, 11))
        self.assertEqual(att.school_id, self.school.id)

    def test_explicit_school_is_not_overwritten(self):
        other = School.objects.create(
            name="Other",
            slug="other-attend",
            subdomain="other-attend",
            country_code="FR",
        )
        att = Attendance.objects.create(
            student=self.student,
            classroom=self.classroom,
            date=date(2025, 9, 12),
            status="present",
            school=other,
        )
        att.refresh_from_db()
        # Backfill only fires when school is NULL — an explicit school stands.
        self.assertEqual(att.school_id, other.id)

    def test_update_branch_heals_legacy_null_row(self):
        att = Attendance.objects.create(
            student=self.student,
            classroom=self.classroom,
            date=date(2025, 9, 13),
            status="present",
        )
        # Simulate a legacy row created before the chokepoint (school=NULL),
        # bypassing save() via a queryset update.
        Attendance.objects.filter(pk=att.pk).update(school=None)
        self.assertIsNone(Attendance.objects.get(pk=att.pk).school_id)

        # Re-marking hits update_or_create's UPDATE branch, which saves with
        # update_fields=["status"] — the backfill must add "school" to that set.
        Attendance.objects.update_or_create(
            student=self.student,
            classroom=self.classroom,
            date=date(2025, 9, 13),
            defaults={"status": "absent"},
        )
        att.refresh_from_db()
        self.assertEqual(att.school_id, self.school.id)
        self.assertEqual(att.status, "absent")
