"""N+1 / query-count guard for the term-ranking hot path (Metric #17).

Wave 15 fixed ``classroom_term_rankings`` / ``school_term_rankings`` to bulk-fetch
evaluations and memoize ``AssessmentWeights`` + formula text so query count is
constant in student count (report-card hot path).
"""

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
from apps.evals.models import Evaluation
from apps.evals.services import classroom_term_rankings, school_term_rankings
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.schools.tests.rls_support import enter_rls_bypass_for_test


@tag("tenants_rls")
class TermRankingQueryCountTests(TestCase):
    """Query count must not scale with class size after the bulk ranking fix."""

    def setUp(self):
        # Postgres-lane routing tag only; not an RLS-isolation test -> run under
        # bypass so bound RLS does not deny the seed rows / reads. See rls_support.
        enter_rls_bypass_for_test(self)
        self.school = School.objects.create(
            name="Ranking QC School",
            slug="ranking-qc",
            subdomain="ranking-qc",
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
            school=self.school, name="Science", code="SCI-RQC"
        )
        self.specialty = Specialty.objects.create(
            school=self.school, department=self.dept, name="General", code="GEN-RQC"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Form 3A",
            code="F3A-RQC",
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.sa = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=2,
        )
        teacher_user = User.objects.create_user(
            username="rqc_teacher", password="pass123", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=teacher_user, school=self.school
        )

    def _add_student_with_eval(self, code: str, seq1: int) -> StudentProfile:
        student = StudentProfile.objects.create(
            school=self.school,
            first_name=f"Stu{code}",
            last_name=code,
            student_code=f"RQC-{code}",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )
        Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.sa,
            student=student,
            teacher=self.teacher,
            seq1_score=seq1,
            seq2_score=seq1,
            exam_score=seq1,
        )
        return student

    def _count_classroom_ranking_queries(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            list(classroom_term_rankings(self.classroom, self.term))
        return len(ctx.captured_queries)

    def test_classroom_ranking_query_count_is_constant(self):
        self._add_student_with_eval("A", 15)
        one = self._count_classroom_ranking_queries()

        self._add_student_with_eval("B", 12)
        self._add_student_with_eval("C", 9)
        three = self._count_classroom_ranking_queries()

        self.assertEqual(
            one,
            three,
            "classroom_term_rankings must use a constant query count "
            f"regardless of class size (1 student: {one}, 3 students: {three}).",
        )

    def test_school_ranking_query_count_is_constant(self):
        self._add_student_with_eval("A", 15)
        with CaptureQueriesContext(connection) as ctx_one:
            list(school_term_rankings(self.term))
        one = len(ctx_one.captured_queries)

        self._add_student_with_eval("B", 12)
        self._add_student_with_eval("C", 9)
        with CaptureQueriesContext(connection) as ctx_three:
            list(school_term_rankings(self.term))
        three = len(ctx_three.captured_queries)

        self.assertEqual(
            one,
            three,
            "school_term_rankings must use a constant query count "
            f"(1 student: {one}, 3 students: {three}).",
        )

    def test_classroom_ranking_order_still_correct(self):
        self._add_student_with_eval("Low", 8)
        self._add_student_with_eval("High", 18)
        ranks = classroom_term_rankings(self.classroom, self.term)
        self.assertEqual(len(ranks), 2)
        self.assertGreaterEqual(ranks[0].average, ranks[1].average)
        self.assertEqual(ranks[0].student.last_name, "High")
