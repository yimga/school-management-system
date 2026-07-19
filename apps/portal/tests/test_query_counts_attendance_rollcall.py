"""N+1 / query-count guard for roll-call attendance upsert (Metric #17)."""

from __future__ import annotations

from datetime import date

from django.db import connection
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext

from apps.academics.bulk_attendance import apply_student_status_map, mark_whole_class
from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.people.models import StudentProfile
from apps.schools.models import School


@tag("tenants_rls")
class AttendanceRollcallQueryCountTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Att QC School",
            slug="att-qc",
            subdomain="att-qc",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.dept = Department.objects.create(
            school=self.school, name="General", code="GEN-AQC"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Form 1A",
            code="F1A-AQC",
        )
        self.day = date(2026, 7, 18)

    def _seed_students(self, n: int, *, code_offset: int = 0) -> list[StudentProfile]:
        out = []
        for i in range(n):
            code_i = code_offset + i
            out.append(
                StudentProfile.objects.create(
                    school=self.school,
                    first_name=f"S{code_i}",
                    last_name="QC",
                    student_code=f"AQC-{code_i:03d}",
                    academic_year=self.year,
                    classroom=self.classroom,
                    is_active=True,
                )
            )
        return out

    def test_mark_whole_class_query_count_constant(self):
        self._seed_students(4, code_offset=0)
        with CaptureQueriesContext(connection) as ctx_small:
            mark_whole_class(
                classroom_id=self.classroom.id,
                date_value=self.day,
                default_status="present",
                school_id=self.school.pk,
                emit_signals=False,
            )
        small = len(ctx_small.captured_queries)

        self._seed_students(12, code_offset=100)  # total 16 distinct codes
        with CaptureQueriesContext(connection) as ctx_large:
            mark_whole_class(
                classroom_id=self.classroom.id,
                date_value=date(2026, 7, 19),
                default_status="present",
                school_id=self.school.pk,
                emit_signals=False,
            )
        large = len(ctx_large.captured_queries)

        self.assertEqual(
            small,
            large,
            "mark_whole_class upsert SQL must be constant "
            f"(4 students: {small}, 16 students: {large}).",
        )
        self.assertLessEqual(small, 8)

        with CaptureQueriesContext(connection) as ctx_idem:
            apply_student_status_map(
                classroom_id=self.classroom.id,
                date_value=self.day,
                school_id=self.school.pk,
                statuses={
                    s.id: Attendance.Status.PRESENT
                    for s in StudentProfile.objects.filter(classroom=self.classroom)
                },
                emit_signals=False,
            )
        self.assertLessEqual(len(ctx_idem.captured_queries), 8)

    def test_status_map_create_then_update_idempotent(self):
        students = self._seed_students(6)
        statuses = {s.id: Attendance.Status.PRESENT for s in students}
        first = apply_student_status_map(
            classroom_id=self.classroom.id,
            date_value=self.day,
            school_id=self.school.pk,
            statuses=statuses,
        )
        self.assertEqual(first.created, 6)
        self.assertEqual(
            Attendance.objects.filter(classroom=self.classroom, date=self.day).count(),
            6,
        )

        with CaptureQueriesContext(connection) as ctx:
            second = apply_student_status_map(
                classroom_id=self.classroom.id,
                date_value=self.day,
                school_id=self.school.pk,
                statuses=statuses,
            )
        self.assertEqual(second.created, 0)
        self.assertEqual(second.skipped, 6)
        self.assertLessEqual(len(ctx.captured_queries), 8)

        statuses[students[0].id] = Attendance.Status.ABSENT
        third = apply_student_status_map(
            classroom_id=self.classroom.id,
            date_value=self.day,
            school_id=self.school.pk,
            statuses=statuses,
        )
        self.assertEqual(third.updated, 1)
        row = Attendance.objects.get(
            classroom=self.classroom, date=self.day, student=students[0]
        )
        self.assertEqual(row.status, Attendance.Status.ABSENT)
