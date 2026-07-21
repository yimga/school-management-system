"""The impossible-jump check must compare a grade to the term BEFORE it.

Found by an A-Z audit follow-up (2026-07-16/17).

``GradeValidator._detect_impossible_jump`` never referenced the evaluation's own
term::

    prev_terms = Term.objects.filter(
        academic_year=evaluation.academic_year
    ).order_by("-id")
    ...
    prev_eval = Evaluation.objects.filter(
        student=evaluation.student,
        subject_assignment=evaluation.subject_assignment,
        term__in=prev_terms[:1],
    ).first()

``prev_terms`` is EVERY term of the year ordered by ``-id``, so ``[:1]`` is the
highest-id term -- typically the LAST term -- not the term preceding this
evaluation. There is no ``.exclude(pk=evaluation.pk)`` either. Since
``Evaluation`` is unique per ``(academic_year, term, subject_assignment,
student)``, there is exactly one row per term, so:

  * an evaluation in the FINAL term matched ITSELF -> pct_change 0.0 -> never
    flagged. That is the term that decides promotion.
  * an evaluation in term 1 was compared against term 3 -- the future.

So the tamper check was inert exactly where tampering matters most, and
nonsense everywhere else. ``-id`` is not term order in any case; ``Term.position``
is (``Term.Meta.ordering`` is ``start_date``, and ids follow creation, not the
calendar).

This validator had NO test coverage at all before this file -- nothing in the
codebase exercised ``GradeValidator`` or ``_detect_impossible_jump``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

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
from apps.accounts.models import User
from apps.evals.models import Evaluation
from apps.evals.validators import GradeValidator
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class ImpossibleJumpUsesTheAdjacentTermTests(TestCase):

    def setUp(self):
        # A tenant. The scores below run 40..95, which only validate against a
        # school whose grading scale is a percentage. This fixture used to create
        # NO School at all and relied on ``resolve_school_score_scale`` answering a
        # neutral 100 for "unknown" — that default was the 2.1 defect (it also let a
        # /20 school accept 25), and the unknown case now clamps to the narrow /20
        # bound instead. Naming the school is what a real Evaluation always has;
        # nothing about the impossible-jump assertions below changes.
        self.school = School.objects.create(
            name="Impossible Jump School",
            slug="impossible-jump-school",
            subdomain="impossible-jump-school",
            country_code="US",  # us_letter -> 0..100 axis
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.terms = {}
        for pos, (name, start, end) in enumerate(
            [
                (Term.Name.FIRST, date(2025, 9, 1), date(2025, 12, 1)),
                (Term.Name.SECOND, date(2026, 1, 5), date(2026, 3, 30)),
                (Term.Name.THIRD, date(2026, 4, 5), date(2026, 6, 30)),
            ],
            start=1,
        ):
            self.terms[pos] = Term.objects.create(
                school=self.school,
                name=name, academic_year=self.year, position=pos,
                start_date=start, end_date=end,
            )
        self.department = Department.objects.create(school=self.school, name="Science", code="SCI-IJ")
        self.specialty = Specialty.objects.create(
            school=self.school, name="General", code="GEN-IJ", department=self.department
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            name="Form 1", code="F1-IJ", academic_year=self.year,
            department=self.department,
        )
        self.subject = Subject.objects.create(school=self.school, name="Math IJ")
        self.teacher = TeacherProfile.objects.create(
            school=self.school,
            user=User.objects.create_user(username="ij_teacher", password="p"),
        )
        # One assignment PER TERM: Evaluation.clean() enforces
        # subject_assignment.term == evaluation.term, which is exactly why the
        # old lookup (matching on subject_assignment across terms) could never
        # find anything.
        self.assignments = {
            pos: SubjectAssignment.objects.create(
                school=self.school,
                academic_year=self.year, term=self.terms[pos],
                classroom=self.classroom, specialty=self.specialty,
                subject=self.subject, coefficient=1,
            )
            for pos in self.terms
        }
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Jump", last_name="Student", student_code="IJ-001",
            academic_year=self.year, classroom=self.classroom,
            specialty=self.specialty,
        )
        self.validator = GradeValidator()

    def _evaluate(self, position: int, score: str):
        """final_score is DERIVED, so drive it via the component scores.

        Every component is set to the same value, so any weighting resolves to
        exactly that number and the jump ratios under test stay meaningful.
        """
        return Evaluation.objects.create(
            academic_year=self.year,
            term=self.terms[position],
            subject_assignment=self.assignments[position],
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal(score),
            seq2_score=Decimal(score),
            exam_score=Decimal(score),
        )

    def test_a_jump_in_the_final_term_is_flagged(self):
        """The whole point: the term that decides promotion.

        20 -> 80 is a 300% jump. It was invisible because the evaluation was
        compared against itself.
        """
        self._evaluate(2, "20.00")
        final = self._evaluate(3, "80.00")
        self.assertTrue(
            self.validator._detect_impossible_jump(final),
            "a 20 -> 80 jump in the FINAL term was not flagged -- the check "
            "compared the evaluation to itself, so grade tampering in the "
            "promotion-deciding term is certified 'validated'",
        )

    def test_a_jump_in_a_middle_term_is_flagged(self):
        self._evaluate(1, "20.00")
        second = self._evaluate(2, "80.00")
        self.assertTrue(self.validator._detect_impossible_jump(second))

    def test_a_normal_movement_is_not_flagged(self):
        self._evaluate(2, "50.00")
        final = self._evaluate(3, "55.00")
        self.assertFalse(
            self.validator._detect_impossible_jump(final),
            "a 10% movement must not be flagged -- a checker that cries wolf "
            "gets ignored",
        )

    def test_the_first_term_has_nothing_to_compare_against(self):
        first = self._evaluate(1, "90.00")
        self.assertFalse(
            self.validator._detect_impossible_jump(first),
            "term 1 has no preceding term; it must not be compared against a "
            "LATER one",
        )

    def test_it_does_not_compare_against_a_future_term(self):
        """Term 1 must not be judged against term 3."""
        self._evaluate(3, "90.00")  # a future term exists, with a wild score
        first = self._evaluate(1, "10.00")
        self.assertFalse(
            self.validator._detect_impossible_jump(first),
            "term 1 was compared against term 3 -- the future -- because "
            "prev_terms ordered by -id and ignored the evaluation's own term",
        )

    def test_a_gap_term_still_finds_the_nearest_earlier_term(self):
        """Term 2 missing: term 3 compares against term 1, not itself."""
        self._evaluate(1, "20.00")
        final = self._evaluate(3, "80.00")
        self.assertTrue(
            self.validator._detect_impossible_jump(final),
            "with no term-2 row, the nearest EARLIER evaluation is term 1",
        )
