"""N+1 / query-count guard for the term-ranking hot path -- AND documentation of a
REAL, PRE-EXISTING N+1 that BUILD-D found during the metric-#17 audit (NOT fixed here,
flagged for the owner).

Metric #17 (Performance). The classroom / school term-ranking functions are on the
report-card term context hot path: ``apps.reports.services.term_report_context``
(services.py:875-876) calls BOTH ``classroom_term_rankings(student.classroom, term)``
AND ``school_term_rankings(term)`` on every report-card render.

=== REAL N+1 FOUND (apps/evals/services.py:75-106) -- documented, NOT fixed ===

    def classroom_term_rankings(classroom, term):
        students = StudentProfile.objects.filter(...).select_related("classroom")  # 1 query
        for s in students:
            ... scores=[student_term_average(s, term)]                            # 1 query / student
        ...

    def student_term_average(student, term):                                      # services.py:56
        evals = Evaluation.objects.filter(student=student, term=term)             # <-- per-student
                                  .select_related("subject_assignment")
        ...

So ``classroom_term_rankings`` issues 1 (student list) + N (one Evaluation query per
student) queries -- a classic O(students) N+1. ``school_term_rankings`` (services.py:94)
has the SAME shape across the whole school. On the report-card path BOTH run, so a class
of N students costs ~2N + overhead Evaluation queries per single student's report card.

=== MODERATOR ADDENDUM (PROMPT-B re-verification): the N+1 is DEEPER than the above ===

The per-student cost is NOT one query -- it is ~THREE. ``student_term_average`` reads
``e.total_score`` (apps/evals/models.py:767), a Python ``@property`` that calls
``compute_evaluation_total_score`` (grade_computation.py:98), which per evaluation:
  (a) ``AssessmentWeights.get_for(year, classroom, term)`` -- a ``.filter().first()``
      with NO caching (models.py:329) -> +1 query per evaluation, and
  (b) ``_resolve_formula_text`` -> ``GradingScale.objects.filter(school=...)``
      (grade_computation.py:31) -> +1 query per evaluation.
So a class of N students costs ~3N queries, and ``school_term_rankings`` on the
report-card path multiplies that across the whole school (O(students^2) for a batch).

The naive ``.values(...).annotate(...)`` fix DOES NOT WORK: ``total_score`` is a computed
Python property (formula engine), not a DB column, so it cannot be aggregated in SQL.
The correct, behaviour-preserving fix (FUTURE, test-backed wave -- deliberately NOT done
blind in a no-test-execution env because this is grade-correctness-critical code):
  1. bulk-fetch all evaluations for the student set in ONE query
     (``Evaluation.objects.filter(student_id__in=[...], term=term)
       .select_related("subject_assignment", "subject_assignment__classroom")``),
  2. memoize ``AssessmentWeights.get_for`` per ``(academic_year_id, classroom_id, term_id)``
     and the resolved formula text per ``school_id`` for the duration of the call,
  3. pass the memoized ``weights=`` into ``compute_evaluation_total_score`` (its line 102
     ``if weights is None`` skips the get_for query when weights are supplied),
which collapses both functions to a constant number of queries in the STUDENT count
(bounded by distinct classrooms for the school-wide path). Only then enable
``test_DESIRED_*`` below.

The tests below pin the CURRENT (intentionally-bad) behaviour so that:
  (a) the N+1 is locked & visible in CI (a count that already scales with N), and
  (b) when the owner fixes it, ``test_DESIRED_*`` (currently skipped) is the spec to
      flip on, and ``test_CURRENT_*`` will start failing -- a loud, intended signal to
      update this guard to the new constant-count contract.

CI: tagged for the Postgres lane. Will NOT run in the BUILD-D local env (py3.14 + 1071
migrations + OneDrive) -- expected; these are CI-pending.
"""

from __future__ import annotations

import unittest
from datetime import date

from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.db import connection

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


@tag("tenants_rls")  # routes the file into a Postgres CI lane
class TermRankingQueryCountTests(TestCase):
    """Locks the current per-student N+1 in the ranking path and specs the fix."""

    def setUp(self):
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
            # force full evaluation (function already returns a list, but be explicit)
            list(classroom_term_rankings(self.classroom, self.term))
        return len(ctx.captured_queries)

    # ----- CURRENT behaviour: the N+1 is real and scales with N (locked) ---------

    def test_CURRENT_classroom_ranking_query_count_scales_with_students(self):
        """DOCUMENTS THE BUG: adding 2 students adds (at least) 2 queries.

        This is the live, pre-existing N+1 (services.py:81 calls student_term_average,
        services.py:58 fires one Evaluation query per student). BUILD-D is test-only,
        so this asserts the CURRENT bad behaviour rather than fixing it. When the owner
        batches the per-student averages into one query, this test SHOULD start failing
        -- that is the intended signal to flip on test_DESIRED_* below.
        """
        self._add_student_with_eval("A", 15)
        one = self._count_classroom_ranking_queries()

        self._add_student_with_eval("B", 12)
        self._add_student_with_eval("C", 9)
        three = self._count_classroom_ranking_queries()

        # Per-student Evaluation query => count grows by ~1 per added student.
        self.assertGreater(
            three,
            one,
            "Expected the CURRENT per-student N+1 to make the 3-student count exceed "
            f"the 1-student count (1: {one}, 3: {three}). If these are now EQUAL, the "
            "N+1 has been FIXED -- delete this CURRENT test and enable test_DESIRED_*.",
        )
        # Pin the scaling shape: at least 2 extra queries for 2 extra students.
        self.assertGreaterEqual(
            three - one,
            2,
            f"Expected >=2 extra queries for 2 extra students (delta={three - one}).",
        )

    # ----- DESIRED behaviour after a future fix (spec; skipped until then) --------

    @unittest.skip(
        "PENDING OWNER FIX of the classroom_term_rankings N+1 (apps/evals/services.py:75). "
        "Enable this and delete test_CURRENT_* once per-student averages are aggregated "
        "into a single query. BUILD-D is test-only and did NOT change the source."
    )
    def test_DESIRED_classroom_ranking_query_count_is_constant(self):
        """SPEC: once fixed, query count must NOT scale with student count."""
        self._add_student_with_eval("A", 15)
        one = self._count_classroom_ranking_queries()

        self._add_student_with_eval("B", 12)
        self._add_student_with_eval("C", 9)
        three = self._count_classroom_ranking_queries()

        self.assertEqual(
            one,
            three,
            "After the fix, classroom_term_rankings must use a constant query count "
            f"regardless of class size (1 student: {one}, 3 students: {three}).",
        )

    @unittest.skip(
        "PENDING OWNER FIX of the school_term_rankings N+1 (apps/evals/services.py:94). "
        "Same per-student N+1 shape as classroom_term_rankings; flip on when batched."
    )
    def test_DESIRED_school_ranking_query_count_is_constant(self):
        """SPEC: school-wide ranking must also be constant-query after the fix."""
        self._add_student_with_eval("A", 15)
        with CaptureQueriesContext(connection) as ctx_one:
            list(school_term_rankings(self.term))
        one = len(ctx_one.captured_queries)

        self._add_student_with_eval("B", 12)
        self._add_student_with_eval("C", 9)
        with CaptureQueriesContext(connection) as ctx_three:
            list(school_term_rankings(self.term))
        three = len(ctx_three.captured_queries)

        self.assertEqual(one, three)
