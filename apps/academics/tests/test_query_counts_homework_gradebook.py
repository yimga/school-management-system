"""N+1 / query-count REGRESSION guard for the homework gradebook hot read path.

Metric #17 (Performance). This is a SAFETY NET written by BUILD-D: it asserts the
query count of ``apps.academics.lms_services.homework_gradebook_for`` does NOT scale
with the number of students or published assignments in the class. A future change
that drops the bulk ``sub_map`` prefetch (lms_services.py:444-449) and instead loads
a submission per (student, assignment) cell would reintroduce an O(students*assignments)
N+1 and fail this test.

Why this path is hot: the teacher gradebook renders a students x published-assignments
matrix for every class, on every gradebook page load.

Audit (as of 2026-06-26, apps/academics/lms_services.py:417-482):
  * assignments  -> ONE query  (.filter(...).select_related("subject"))            line 428
  * students     -> ONE query  (StudentProfile.objects.filter(...).order_by(...))   line 438
  * submissions  -> ONE query  (LMSSubmission.objects.filter(assignment__in=...,
                                student__in=...).select_related("student"))         line 446
                    bulk-loaded into sub_map; the per-row Python loop then reads
                    from sub_map and never hits the DB again.
So the path is ALREADY optimized: the count is CONSTANT (a small fixed number of
queries) regardless of class size. These tests pin that property rather than a
magic number, by asserting the count for a 1-student/1-assignment class EQUALS the
count for a 3-student/3-assignment class.

CI: runs in the Postgres lane (django-tests-postgres.yml already globs apps/academics/**).
Will NOT run in the BUILD-D local env (py3.14 + 1071 migrations + OneDrive) -- expected.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.academics.lms_services import (
    grade_submission,
    homework_gradebook_for,
    submit_assignment,
)
from apps.academics.models import AcademicYear, Classroom, Department, Subject, Term
from apps.academics.models_lms import LMSAssignment
from apps.accounts.models import User
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.schools.tests.rls_support import enter_rls_bypass_for_test


@tag("tenants_rls")  # routes the file into the Postgres CI lane (django-tests-postgres.yml)
class HomeworkGradebookQueryCountTests(TestCase):
    """The gradebook matrix must use a constant number of queries (no per-cell N+1)."""

    def setUp(self):
        # Postgres-lane routing tag only; not an RLS-isolation test -> run under
        # bypass so bound RLS does not deny the seed rows / reads. See rls_support.
        enter_rls_bypass_for_test(self)
        self.school = School.objects.create(
            name="Gradebook QC School",
            slug="gradebook-qc",
            subdomain="gradebook-qc",
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
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        self.dept = Department.objects.create(
            school=self.school, name="Math", code="M-GBQC"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Grade 10",
            code="G10-GBQC",
        )
        self.subject = Subject.objects.create(school=self.school, name="Algebra")
        teacher_user = User.objects.create_user(
            username="gbqc_teacher",
            email="gbqc_teacher@test.com",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            user=teacher_user, school=self.school
        )

    def _make_student(self, code: str) -> StudentProfile:
        return StudentProfile.objects.create(
            first_name=f"Stu{code}",
            last_name=code,
            student_code=f"GBQC-{code}",
            school=self.school,
            classroom=self.classroom,
            academic_year=self.year,
            is_active=True,
        )

    def _make_published_assignment(self, title: str) -> LMSAssignment:
        return LMSAssignment.objects.create(
            school=self.school,
            classroom=self.classroom,
            subject=self.subject,
            term=self.term,
            teacher=self.teacher,
            title=title,
            instructions="Do the homework.",
            status=LMSAssignment.Status.PUBLISHED,
            due_at=timezone.now() + timedelta(days=3),
        )

    def _build_and_grade(self, students, assignments):
        """Submit+grade every (student, assignment) so sub_map is fully populated --
        the worst case for an N+1 (a submission exists for every cell)."""
        for student in students:
            for a in assignments:
                sub, _ = submit_assignment(
                    assignment=a, student=student, content="answer"
                )
                grade_submission(
                    submission=sub, score=70, graded_by=self.teacher.user
                )

    def _count_gradebook_queries(self) -> int:
        # Materialize the rows fully (homework_gradebook_for already returns a list,
        # but iterate the cells to be certain nothing is lazily deferred).
        with CaptureQueriesContext(connection) as ctx:
            gb = homework_gradebook_for(
                school=self.school, teacher=self.teacher, classroom=self.classroom
            )
            for row in gb["rows"]:
                for cell in row["cells"]:
                    _ = cell["score"], cell["status"], cell["submission"]
        return len(ctx.captured_queries)

    def test_query_count_is_constant_as_students_grow(self):
        """1 student/2 assignments vs 3 students/2 assignments => SAME query count.

        If a future edit replaces the bulk sub_map load with a per-(student,assignment)
        lookup, the 3-student count would jump above the 1-student count and fail.
        """
        a1 = self._make_published_assignment("HW 1")
        a2 = self._make_published_assignment("HW 2")

        s1 = self._make_student("A")
        self._build_and_grade([s1], [a1, a2])
        small = self._count_gradebook_queries()

        s2 = self._make_student("B")
        s3 = self._make_student("C")
        self._build_and_grade([s2, s3], [a1, a2])
        large = self._count_gradebook_queries()

        self.assertEqual(
            small,
            large,
            "homework_gradebook_for query count scaled with student count -- "
            f"N+1 regression (1 student: {small} queries, 3 students: {large}). "
            "The bulk sub_map prefetch in lms_services.py was likely dropped.",
        )

    def test_query_count_is_constant_as_assignments_grow(self):
        """1 assignment vs 3 assignments (same 2 students) => SAME query count."""
        s1 = self._make_student("A")
        s2 = self._make_student("B")

        a1 = self._make_published_assignment("HW 1")
        self._build_and_grade([s1, s2], [a1])
        small = self._count_gradebook_queries()

        a2 = self._make_published_assignment("HW 2")
        a3 = self._make_published_assignment("HW 3")
        self._build_and_grade([s1, s2], [a2, a3])
        large = self._count_gradebook_queries()

        self.assertEqual(
            small,
            large,
            "homework_gradebook_for query count scaled with assignment count -- "
            f"N+1 regression (1 assignment: {small}, 3 assignments: {large}).",
        )

    def test_gradebook_uses_small_fixed_query_budget(self):
        """Belt-and-suspenders absolute ceiling so a constant-but-huge count is also caught.

        The service issues a small, fixed set of queries: assignments + students +
        submissions, plus a few framework/savepoint queries. 8 is a generous ceiling
        that still flags a per-row N+1 on a 3x3 matrix (which would be >= ~11).
        """
        students = [self._make_student(c) for c in ("A", "B", "C")]
        assignments = [self._make_published_assignment(f"HW {i}") for i in range(3)]
        self._build_and_grade(students, assignments)

        count = self._count_gradebook_queries()
        self.assertLessEqual(
            count,
            8,
            f"homework_gradebook_for used {count} queries for a 3x3 matrix; "
            "expected a small fixed budget (assignments + students + submissions). "
            "A per-cell lookup N+1 would blow this ceiling.",
        )
