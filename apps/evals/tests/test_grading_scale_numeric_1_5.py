"""Phase A of the world-scale bridge: operational support for the post-Soviet 1–5 scale.

The 1–5 scale fits the engine's existing 5-band A–E numeric model, so it works through
the generic ``GradeConverter`` (score_scale=5 + thresholds) with NO special-casing. These
no-DB tests prove the new scale converts correctly end-to-end AND that the four pre-existing
scales (numeric_0_20, letter_a_e, gpa_4_0, percentage) are byte-for-byte unchanged — the
hard invariant when touching the live-grading core.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.evals.grading import (
    ASSESSMENT_WEIGHTS_SCALE_MAP,
    GRADING_SCALES,
    convert_score,
    scale_for_assessment_weights,
)
from apps.evals.grading_provisioning import (
    _VALID_SCALE_TYPES,
    _normalize_scale_type,
    _scale_config,
)
from apps.evals.grading_wizard_kernel import _SCALE_TYPE_MAP
from apps.evals.models import GRADING_SCALE_BANDS, default_bands_for_scale
from apps.evals.validators import GradeConverter


class _StubWeights:
    """Minimal AssessmentWeights stand-in built from a GRADING_SCALE_BANDS row."""

    def __init__(self, scale_type: str):
        bands = GRADING_SCALE_BANDS[scale_type]
        self.grading_scale = scale_type
        self.score_scale = bands["score_scale"]
        self.grade_a_min = bands["a"]
        self.grade_b_min = bands["b"]
        self.grade_c_min = bands["c"]
        self.grade_d_min = bands["d"]
        self.grade_e_min = bands["e"]


class Numeric1to5OperationalTests(SimpleTestCase):
    def test_bands_registered_with_pass_at_three(self):
        bands = GRADING_SCALE_BANDS["numeric_1_5"]
        self.assertEqual(bands["score_scale"], 5)
        # _scale_config derives pass_threshold from the lowest passing band (d).
        cfg = _scale_config("numeric_1_5")
        self.assertEqual(cfg["score_scale"], 5)
        self.assertEqual(cfg["pass_threshold"], 3.0)

    def test_grade_converter_letters_at_boundaries(self):
        conv = GradeConverter(_StubWeights("numeric_1_5"))
        self.assertEqual(conv.numeric_to_letter(Decimal("5")), "A")
        self.assertEqual(conv.numeric_to_letter(Decimal("4.5")), "A")
        self.assertEqual(conv.numeric_to_letter(Decimal("4")), "B")
        self.assertEqual(conv.numeric_to_letter(Decimal("3.5")), "C")
        self.assertEqual(conv.numeric_to_letter(Decimal("3")), "D")  # lowest pass
        self.assertEqual(conv.numeric_to_letter(Decimal("2")), "E")  # fail

    def test_grade_converter_gpa_and_percentage_use_scale_5(self):
        conv = GradeConverter(_StubWeights("numeric_1_5"))
        self.assertAlmostEqual(conv.numeric_to_gpa(Decimal("5")), 4.0)
        self.assertAlmostEqual(conv.numeric_to_gpa(Decimal("4")), 3.2)
        self.assertAlmostEqual(conv.numeric_to_percentage(Decimal("3")), 60.0)
        self.assertAlmostEqual(conv.numeric_to_percentage(Decimal("5")), 100.0)

    def test_resolvers_accept_new_scale(self):
        self.assertIn("numeric_1_5", _VALID_SCALE_TYPES)
        self.assertEqual(_normalize_scale_type("numeric_1_5"), "numeric_1_5")
        self.assertEqual(_normalize_scale_type("1-5"), "numeric_1_5")  # via wizard map
        self.assertEqual(_SCALE_TYPE_MAP["post_soviet"], "numeric_1_5")

    def test_display_layer_maps_and_converts(self):
        self.assertIn("1-5", GRADING_SCALES)
        self.assertEqual(ASSESSMENT_WEIGHTS_SCALE_MAP["numeric_1_5"], "1-5")
        self.assertEqual(scale_for_assessment_weights(_StubWeights("numeric_1_5")), "1-5")
        # A 3/5 is 60% — cross-scale conversion must agree with the operational %.
        self.assertEqual(convert_score(3, "1-5", "0-100"), Decimal("60.00"))
        self.assertEqual(convert_score(3, "1-5", "0-20"), Decimal("12.00"))

    def test_default_bands_for_unknown_scale_still_falls_back(self):
        # Safety net unchanged: an unknown scale yields the numeric_0_20 bands, never raises.
        self.assertEqual(default_bands_for_scale("does_not_exist"), GRADING_SCALE_BANDS["numeric_0_20"])


class ExistingFourScalesUnchangedTests(SimpleTestCase):
    """Regression lock: the bridge must not perturb the four shipped scales."""

    def test_existing_bands_byte_for_byte(self):
        self.assertEqual(GRADING_SCALE_BANDS["numeric_0_20"], {"a": 18, "b": 16, "c": 14, "d": 10, "e": 0, "score_scale": 20})
        self.assertEqual(GRADING_SCALE_BANDS["letter_a_e"], {"a": 18, "b": 16, "c": 14, "d": 10, "e": 0, "score_scale": 20})
        self.assertEqual(GRADING_SCALE_BANDS["gpa_4_0"], {"a": 3.5, "b": 3.0, "c": 2.0, "d": 1.0, "e": 0, "score_scale": 4})
        self.assertEqual(GRADING_SCALE_BANDS["percentage"], {"a": 80, "b": 70, "c": 60, "d": 50, "e": 0, "score_scale": 100})

    def test_existing_display_map_unchanged(self):
        for k, v in {"numeric_0_20": "0-20", "letter_a_e": "0-20", "gpa_4_0": "gpa", "percentage": "0-100"}.items():
            self.assertEqual(ASSESSMENT_WEIGHTS_SCALE_MAP[k], v)

    def test_existing_converter_outputs_unchanged(self):
        # A 0–20 school: 15 → B (b_min 16? no — 15 < 16, ≥14 → C). Lock the exact mapping.
        conv = GradeConverter(_StubWeights("numeric_0_20"))
        self.assertEqual(conv.numeric_to_letter(Decimal("18")), "A")
        self.assertEqual(conv.numeric_to_letter(Decimal("15")), "C")
        self.assertEqual(conv.numeric_to_letter(Decimal("10")), "D")
        self.assertAlmostEqual(conv.numeric_to_percentage(Decimal("10")), 50.0)
