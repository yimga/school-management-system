"""N+1 / query-count guard for teacher-dashboard completion spotlight (Metric #17)."""

from __future__ import annotations

from datetime import date

from django.db import connection
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.models import Evaluation, TeacherAssignment
from apps.evals.services import (
    completion_for_assignment,
    completion_for_assignments_bulk,
)
from apps.people.models import StudentProfile, TeacherProfile
from apps.portal.services import _assignment_completion_spotlight
from apps.schools.models import School
from apps.schools.tests.rls_support import enter_rls_bypass_for_test


@tag("tenants_rls")
class TeacherCompletionSpotlightQueryCountTests(TestCase):
    def setUp(self):
        # Postgres-lane routing tag only; not an RLS-isolation test -> run under
        # bypass so bound RLS does not deny the seed rows / reads. See rls_support.
        enter_rls_bypass_for_test(self)
        self.school = School.objects.create(
            name="Completion QC School",
            slug="completion-qc",
            subdomain="completion-qc",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="FIRST",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        self.dept = Department.objects.create(
            school=self.school, name="Science", code="SCI-CQC"
        )
        self.specialty = Specialty.objects.create(
            school=self.school, department=self.dept, name="General", code="GEN-CQC"
        )
        teacher_user = User.objects.create_user(
            username="cqc_teacher", password="pass123", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=teacher_user, school=self.school
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Form 3A",
            code="F3A-CQC",
        )
        self.assignments: list[TeacherAssignment] = []

    def _add_assignment(self, subject_name: str) -> TeacherAssignment:
        subject = Subject.objects.create(school=self.school, name=subject_name)
        sa = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=subject,
            coefficient=1,
        )
        ta = TeacherAssignment.objects.create(
            school=self.school,
            teacher=self.teacher,
            academic_year=self.year,
            subject_assignment=sa,
        )
        self.assignments.append(ta)
        return ta

    def _add_student(self, code: str, with_eval_on: SubjectAssignment | None = None):
        student = StudentProfile.objects.create(
            school=self.school,
            first_name=f"Stu{code}",
            last_name=code,
            student_code=f"CQC-{code}",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )
        if with_eval_on is not None:
            Evaluation.objects.create(
                academic_year=self.year,
                term=self.term,
                subject_assignment=with_eval_on,
                student=student,
                teacher=self.teacher,
                seq1_score=12,
            )
        return student

    def test_bulk_matches_per_assignment(self):
        ta1 = self._add_assignment("Math")
        ta2 = self._add_assignment("Physics")
        self._add_student("A", with_eval_on=ta1.subject_assignment)
        self._add_student("B")
        sas = [ta1.subject_assignment, ta2.subject_assignment]
        bulk = completion_for_assignments_bulk(sas, self.term)
        for sa in sas:
            single = completion_for_assignment(sa, self.term)
            self.assertEqual(bulk[sa.pk].total, single.total)
            self.assertEqual(bulk[sa.pk].completed, single.completed)
            self.assertEqual(bulk[sa.pk].pending, single.pending)
            self.assertEqual(bulk[sa.pk].completion_pct, single.completion_pct)

    def test_spotlight_query_count_constant_as_assignments_grow(self):
        ta1 = self._add_assignment("Math")
        self._add_student("A", with_eval_on=ta1.subject_assignment)
        qs = (
            TeacherAssignment.objects.filter(pk__in=[ta1.pk])
            .select_related(
                "subject_assignment__subject",
                "subject_assignment__classroom",
            )
        )
        with CaptureQueriesContext(connection) as ctx_one:
            _assignment_completion_spotlight(list(qs), self.term)
        one = len(ctx_one.captured_queries)

        for name in ("Physics", "Chem", "Bio"):
            self._add_assignment(name)
        qs_many = (
            TeacherAssignment.objects.filter(
                pk__in=[a.pk for a in self.assignments]
            ).select_related(
                "subject_assignment__subject",
                "subject_assignment__classroom",
            )
        )
        with CaptureQueriesContext(connection) as ctx_many:
            _assignment_completion_spotlight(list(qs_many), self.term)
        many = len(ctx_many.captured_queries)

        self.assertEqual(
            one,
            many,
            "spotlight must use constant queries regardless of assignment count "
            f"(1 assignment: {one}, {len(self.assignments)} assignments: {many}).",
        )
        self.assertLessEqual(one, 4)
