"""Wave S-A (v3.96.1 — 2026-05-26) — Bulk gradebook + rubric editor tests."""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.evals.bulk_gradebook import (
    BulkGradeApplyResult,
    BulkGradeRow,
    Criterion,
    GradeParseError,
    GradeScale,
    Level,
    Rubric,
    RubricValidationError,
    apply_bulk_grades,
    parse_grade_value,
    score_with_rubric,
    validate_bulk_grade_rows,
    validate_rubric,
)


class ParseGradeValueTests(SimpleTestCase):

    def test_percent_format(self):
        self.assertEqual(
            parse_grade_value("85%", GradeScale(kind="percent")), Decimal("85"),
        )

    def test_number_under_percent_scale(self):
        self.assertEqual(
            parse_grade_value("85", GradeScale(kind="percent")), Decimal("85"),
        )

    def test_fraction(self):
        self.assertEqual(
            parse_grade_value("17/20", GradeScale(kind="points", max_points=Decimal("20"))),
            Decimal("85"),
        )

    def test_letter_grade(self):
        self.assertEqual(
            parse_grade_value("B+", GradeScale(kind="letter")), Decimal("87"),
        )

    def test_gpa4_grade(self):
        self.assertEqual(
            parse_grade_value("3.7", GradeScale(kind="gpa4")), Decimal("90"),
        )

    def test_points_scale_conversion(self):
        self.assertEqual(
            parse_grade_value("9", GradeScale(kind="points", max_points=Decimal("10"))),
            Decimal("90"),
        )

    def test_clamps_above_100(self):
        self.assertEqual(
            parse_grade_value("150", GradeScale(kind="percent")), Decimal("100"),
        )

    def test_clamps_below_0(self):
        # Fraction can't go negative; use raw percent-scale wrapper.
        self.assertEqual(
            parse_grade_value("0", GradeScale(kind="percent")), Decimal("0"),
        )

    def test_unknown_letter_raises(self):
        with self.assertRaises(GradeParseError):
            parse_grade_value("Z", GradeScale(kind="letter"))

    def test_blank_raises(self):
        with self.assertRaises(GradeParseError):
            parse_grade_value("", GradeScale(kind="percent"))

    def test_zero_denominator_raises(self):
        with self.assertRaises(GradeParseError):
            parse_grade_value("5/0", GradeScale(kind="percent"))


class ValidateBulkGradeRowsTests(SimpleTestCase):

    def test_happy_path(self):
        scale = GradeScale(kind="percent")
        rows = [
            BulkGradeRow(student_id=1, raw_value="85"),
            BulkGradeRow(student_id=2, raw_value="92%"),
        ]
        v = validate_bulk_grade_rows(rows, scale)
        self.assertTrue(v.is_valid)
        self.assertEqual(v.accepted_count, 2)
        self.assertEqual(v.accepted[0][1], Decimal("85"))

    def test_duplicates_flagged(self):
        scale = GradeScale(kind="percent")
        v = validate_bulk_grade_rows(
            [BulkGradeRow(1, "85"), BulkGradeRow(1, "90")], scale,
        )
        self.assertFalse(v.is_valid)
        self.assertTrue(any(e.reason == "duplicate" for e in v.errors))

    def test_invalid_value_does_not_block_rest(self):
        scale = GradeScale(kind="percent")
        v = validate_bulk_grade_rows(
            [
                BulkGradeRow(1, "garbage"),
                BulkGradeRow(2, "85"),
            ],
            scale,
        )
        self.assertFalse(v.is_valid)
        # Row 2 should still be accepted (no fail-fast).
        self.assertEqual(v.accepted_count, 1)


class ApplyBulkGradesTests(SimpleTestCase):

    def test_runner_seam(self):
        captured = {}

        def fake_runner(*, assessment_id, accepted):
            captured["assessment_id"] = assessment_id
            captured["count"] = len(accepted)
            return BulkGradeApplyResult(created=len(accepted))

        out = apply_bulk_grades(
            assessment_id=99,
            rows=[BulkGradeRow(1, "85"), BulkGradeRow(2, "90")],
            scale=GradeScale(kind="percent"),
            db_runner=fake_runner,
        )
        self.assertEqual(out.created, 2)
        self.assertEqual(captured["assessment_id"], 99)
        self.assertEqual(captured["count"], 2)

    def test_validation_fail_short_circuits(self):
        out = apply_bulk_grades(
            assessment_id=99,
            rows=[BulkGradeRow(1, "garbage")],
            scale=GradeScale(kind="percent"),
            db_runner=lambda **kw: BulkGradeApplyResult(),
        )
        self.assertEqual(out.created, 0)
        self.assertTrue(out.errors)


def _good_rubric() -> Rubric:
    return Rubric(
        rubric_id="essay-v1",
        name="Persuasive essay",
        criteria=(
            Criterion(
                key="thesis", label="Thesis clarity", weight=Decimal("0.30"),
                levels=(
                    Level(key="1", label="Beginning", points=Decimal("1")),
                    Level(key="2", label="Developing", points=Decimal("2")),
                    Level(key="3", label="Proficient", points=Decimal("3")),
                    Level(key="4", label="Exemplary", points=Decimal("4")),
                ),
            ),
            Criterion(
                key="evidence", label="Evidence", weight=Decimal("0.40"),
                levels=(
                    Level(key="1", label="Beginning", points=Decimal("1")),
                    Level(key="4", label="Exemplary", points=Decimal("4")),
                ),
            ),
            Criterion(
                key="mechanics", label="Mechanics", weight=Decimal("0.30"),
                levels=(
                    Level(key="1", label="Beginning", points=Decimal("1")),
                    Level(key="3", label="Proficient", points=Decimal("3")),
                ),
            ),
        ),
    )


class ValidateRubricTests(SimpleTestCase):

    def test_good_rubric_passes(self):
        validate_rubric(_good_rubric())

    def test_empty_criteria_fails(self):
        bad = Rubric(rubric_id="x", name="x", criteria=())
        with self.assertRaises(RubricValidationError):
            validate_rubric(bad)

    def test_weights_not_summing_to_one_fails(self):
        rub = _good_rubric()
        # Replace weights so they sum to 0.5
        bad = Rubric(
            rubric_id=rub.rubric_id, name=rub.name,
            criteria=tuple(
                Criterion(c.key, c.label, Decimal("0.10"), c.levels)
                for c in rub.criteria
            ),
        )
        with self.assertRaises(RubricValidationError):
            validate_rubric(bad)

    def test_duplicate_criterion_keys_fails(self):
        c = _good_rubric().criteria[0]
        bad = Rubric(
            rubric_id="x", name="x",
            criteria=(c, c, c),
        )
        with self.assertRaises(RubricValidationError):
            validate_rubric(bad)

    def test_criterion_with_zero_max_fails(self):
        bad = Rubric(
            rubric_id="x", name="x",
            criteria=(
                Criterion(
                    key="k", label="K", weight=Decimal("1.0"),
                    levels=(Level(key="z", label="Z", points=Decimal("0")),),
                ),
            ),
        )
        with self.assertRaises(RubricValidationError):
            validate_rubric(bad)


class ScoreWithRubricTests(SimpleTestCase):

    def test_all_levels_4_yields_100(self):
        rub = _good_rubric()
        selections = {"thesis": "4", "evidence": "4", "mechanics": "3"}
        out = score_with_rubric(rubric=rub, selections=selections)
        self.assertEqual(out.errors, [])
        # All criteria at top level → weighted total should be 100.
        self.assertEqual(out.weighted_total_percent, Decimal("100.00"))

    def test_missing_selection_flagged(self):
        rub = _good_rubric()
        out = score_with_rubric(
            rubric=rub, selections={"thesis": "4", "evidence": "4"},
        )
        self.assertTrue(any(
            e.startswith("missing_selection_for_criterion:mechanics")
            for e in out.errors
        ))

    def test_unknown_level_flagged(self):
        rub = _good_rubric()
        out = score_with_rubric(
            rubric=rub,
            selections={"thesis": "99", "evidence": "4", "mechanics": "3"},
        )
        self.assertTrue(any(
            e.startswith("unknown_level_for_criterion:thesis")
            for e in out.errors
        ))

    def test_weighted_total_uses_relative_max(self):
        rub = _good_rubric()
        # evidence: max=4, selecting "1" → 25%. Weight 0.40 → contributes 10.
        # thesis at "4" → 100%, weight 0.30 → contributes 30.
        # mechanics at "3" (max=3) → 100%, weight 0.30 → contributes 30.
        # total = 70.
        out = score_with_rubric(
            rubric=rub,
            selections={"thesis": "4", "evidence": "1", "mechanics": "3"},
        )
        self.assertEqual(out.errors, [])
        self.assertEqual(out.weighted_total_percent, Decimal("70.00"))
