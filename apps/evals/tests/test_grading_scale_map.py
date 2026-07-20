"""
Tests for AssessmentWeights -> grading scale mapping (scale_for_assessment_weights, ASSESSMENT_WEIGHTS_SCALE_MAP).
"""

from unittest.mock import MagicMock

from django.test import TestCase

from apps.evals.grading import (
    ASSESSMENT_WEIGHTS_SCALE_MAP,
    scale_for_assessment_weights,
    get_grade_letter,
)


class ScaleForAssessmentWeightsTests(TestCase):
    def test_none_returns_0_20(self):
        self.assertEqual(scale_for_assessment_weights(None), "0-20")

    def test_numeric_0_20_maps_to_0_20(self):
        w = MagicMock(grading_scale="numeric_0_20")
        self.assertEqual(scale_for_assessment_weights(w), "0-20")

    def test_letter_a_e_maps_to_0_20(self):
        w = MagicMock(grading_scale="letter_a_e")
        self.assertEqual(scale_for_assessment_weights(w), "0-20")

    def test_gpa_4_0_maps_to_gpa(self):
        w = MagicMock(grading_scale="gpa_4_0")
        self.assertEqual(scale_for_assessment_weights(w), "gpa")

    def test_percentage_maps_to_0_100(self):
        w = MagicMock(grading_scale="percentage")
        self.assertEqual(scale_for_assessment_weights(w), "0-100")

    def test_unknown_scale_defaults_to_0_20(self):
        w = MagicMock(grading_scale="unknown")
        self.assertEqual(scale_for_assessment_weights(w), "0-20")

    def test_every_scale_type_has_a_display_mapping(self):
        """The operational↔display contract: EVERY scale must map.

        This used to assert a frozen five-name set, which broke the moment the
        platform grew the ten international scales (french_0_20, ib_1_7,
        uk_gcse_9_1, ...) — a legitimate addition failing a test that was really
        just a snapshot. The invariant worth holding is the one stated in
        ``grading.py``: a ScaleType with no entry here silently falls back to
        0–20, so a French or IB school would be scored on the wrong axis.
        """
        from apps.evals.models import GradingScale

        declared = {choice.value for choice in GradingScale.ScaleType}
        missing = declared - set(ASSESSMENT_WEIGHTS_SCALE_MAP)
        self.assertEqual(
            missing,
            set(),
            f"ScaleType(s) with no display mapping — they would silently score "
            f"on the 0–20 fallback: {sorted(missing)}",
        )

    def test_core_scales_keep_their_historical_display_axis(self):
        """These four are load-bearing; changing one re-scores existing schools."""
        for scale_type, expected in (
            ("numeric_0_20", "0-20"),
            ("letter_a_e", "0-20"),
            ("gpa_4_0", "gpa"),
            ("percentage", "0-100"),
        ):
            with self.subTest(scale_type=scale_type):
                self.assertEqual(ASSESSMENT_WEIGHTS_SCALE_MAP[scale_type], expected)

    def test_numeric_1_5_maps_to_1_5(self):
        w = MagicMock(grading_scale="numeric_1_5")
        self.assertEqual(scale_for_assessment_weights(w), "1-5")


class ScaleIntegrationTests(TestCase):
    """Use scale_for_assessment_weights result with get_grade_letter and format_score."""

    def test_0_20_scale_grade_letter(self):
        scale = scale_for_assessment_weights(MagicMock(grading_scale="numeric_0_20"))
        self.assertEqual(get_grade_letter(18, scale), "A")
        self.assertEqual(get_grade_letter(12, scale), "C")

    def test_0_100_scale_grade_letter(self):
        scale = scale_for_assessment_weights(MagicMock(grading_scale="percentage"))
        self.assertEqual(get_grade_letter(90, scale), "A")
        self.assertEqual(get_grade_letter(65, scale), "D")
