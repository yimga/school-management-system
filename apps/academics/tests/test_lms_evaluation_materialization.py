"""No-DB tests for the homework -> gradebook materialization helpers.

The full upsert path is exercised by DB-backed tests in CI; these lock the pure
logic (scale conversion, component resolution) and the early skip-returns that
never touch the ORM, so they run without the test database.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.academics.lms_services import (
    _convert_homework_score,
    _resolve_homework_eval_component,
    materialize_evaluation_from_submission,
)
from apps.academics.models_lms import LMSSubmission


class ConvertHomeworkScoreTests(SimpleTestCase):
    def test_rescales_100_to_20(self):
        self.assertEqual(_convert_homework_score(80, 100, Decimal("20")), Decimal("16.00"))

    def test_full_marks(self):
        self.assertEqual(_convert_homework_score(100, 100, Decimal("20")), Decimal("20.00"))

    def test_clamps_over_max(self):
        self.assertEqual(_convert_homework_score(120, 100, Decimal("20")), Decimal("20.00"))

    def test_negative_clamped_to_zero(self):
        self.assertEqual(_convert_homework_score(-5, 100, Decimal("20")), Decimal("0.00"))

    def test_zero_points_possible_is_safe(self):
        self.assertEqual(_convert_homework_score(50, 0, Decimal("20")), Decimal("0"))

    def test_same_scale_is_identity(self):
        self.assertEqual(_convert_homework_score(17, 20, Decimal("20")), Decimal("17.00"))

    def test_garbage_input_is_zero(self):
        self.assertEqual(_convert_homework_score("x", 100, Decimal("20")), Decimal("0"))


class ResolveComponentTests(SimpleTestCase):
    def test_default_is_disabled(self):
        self.assertEqual(_resolve_homework_eval_component(SimpleNamespace(settings={})), "none")

    def test_unset_school_is_disabled(self):
        self.assertEqual(_resolve_homework_eval_component(SimpleNamespace()), "none")

    def test_explicit_seq1(self):
        school = SimpleNamespace(settings={"lms_homework_eval_component": "seq1"})
        self.assertEqual(_resolve_homework_eval_component(school), "seq1")

    def test_practical(self):
        school = SimpleNamespace(settings={"lms_homework_eval_component": "PRACTICAL"})
        self.assertEqual(_resolve_homework_eval_component(school), "practical")

    def test_bogus_value_is_disabled(self):
        school = SimpleNamespace(settings={"lms_homework_eval_component": "exam_score"})
        self.assertEqual(_resolve_homework_eval_component(school), "none")

    def test_non_dict_settings_safe(self):
        self.assertEqual(_resolve_homework_eval_component(SimpleNamespace(settings="oops")), "none")


class MaterializeSkipPathTests(SimpleTestCase):
    """Early returns that never touch the ORM — safe under SimpleTestCase."""

    def _submission(self, *, score, status, school_settings=None):
        school = SimpleNamespace(settings=school_settings if school_settings is not None else {})
        assignment = SimpleNamespace(school=school, term=None, subject_id=1, points_possible=100)
        return SimpleNamespace(
            assignment=assignment,
            school=school,
            student=SimpleNamespace(academic_year=None),
            score=score,
            status=status,
        )

    def test_ungraded_skips(self):
        sub = self._submission(score=None, status=LMSSubmission.Status.SUBMITTED)
        self.assertEqual(
            materialize_evaluation_from_submission(submission=sub)["reason"], "not_graded"
        )

    def test_disabled_school_skips_before_orm(self):
        # GRADED + score, but school hasn't opted in -> 'disabled', no ORM touched.
        sub = self._submission(score=90, status=LMSSubmission.Status.GRADED)
        self.assertEqual(
            materialize_evaluation_from_submission(submission=sub)["reason"], "disabled"
        )

    def test_opted_in_but_no_term_skips(self):
        sub = self._submission(
            score=90,
            status=LMSSubmission.Status.GRADED,
            school_settings={"lms_homework_eval_component": "seq1"},
        )
        self.assertEqual(
            materialize_evaluation_from_submission(submission=sub)["reason"], "no_term"
        )
