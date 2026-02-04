"""
Tests for AssessmentWeights -> grading scale mapping (scale_for_assessment_weights, ASSESSMENT_WEIGHTS_SCALE_MAP).
"""
from unittest.mock import MagicMock

from django.test import TestCase

from apps.evals.grading import (
    ASSESSMENT_WEIGHTS_SCALE_MAP,
    scale_for_assessment_weights,
    get_grade_letter,
    format_score,
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

    def test_map_keys_complete(self):
        self.assertEqual(
            set(ASSESSMENT_WEIGHTS_SCALE_MAP.keys()),
            {"numeric_0_20", "letter_a_e", "gpa_4_0", "percentage"},
        )


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
