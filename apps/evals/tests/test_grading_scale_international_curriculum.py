"""International curriculum world scales made first-class computable:
UK GCSE 9–1, IB 1–7, German 1–6 (INVERTED: 1 best), and CBSE 10-point (A1–E2).

These were already in the registry + durable seed (GRADE_SCALE_SEED_DEFAULTS /
registries migration 0008 / REQUIRED_CODES) and listed as AssessmentWeights /
GradingScale choices, but the OPERATIONAL band-resolution path had drifted behind:
``resolve_extended_band_label`` could not return a band for German / CBSE at all, the
UK GCSE / IB band tables were sparse/collapsed, and ``REGISTRY_SCALE_TYPE_MAP`` (the
catalog↔engine bridge) was missing every one of them. These no-DB tests prove each
scale now resolves the CORRECT band label for representative scores end-to-end, that
German's inverted direction is honoured (a lower score is a better grade), and that the
bridge / display maps / valid-type sets all include them.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.evals.grading import (
    ASSESSMENT_WEIGHTS_SCALE_MAP,
    REGISTRY_SCALE_TYPE_MAP,
    format_grade_band,
)
from apps.evals.grading_provisioning import _VALID_SCALE_TYPES, _normalize_scale_type
from apps.evals.grading_wizard_kernel import _SCALE_TYPE_MAP
from apps.evals.models import (
    EXTENDED_GRADE_BANDS,
    GRADING_SCALE_BANDS,
    GradingScale,
    resolve_extended_band_label,
)
from apps.evals.validators import GradeConverter

# The four scales this metric makes first-class, with their registry code +
# representative (score -> expected band label) cases on the scale's own axis.
_TARGET_SCALES = {
    "uk_gcse_9_1": {
        "registry_code": "UK_GCSE_9_1",
        "score_scale": 9,
        # 1–9 grade axis, 9 best … 1 worst; every whole grade is its own band.
        "cases": {9: "9", 8: "8", 7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2", 1: "1"},
    },
    "ib_1_7": {
        "registry_code": "IB_1_7",
        "score_scale": 7,
        # 1–7 subject grade, 7 best … 1 worst; full whole-grade bands.
        "cases": {7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2", 1: "1"},
    },
    "cbse_10": {
        "registry_code": "CBSE_10",
        "score_scale": 10,
        # CBSE board letters on the 0–10 grade-point axis: A1=10 … D=4, then E1/E2 fail.
        "cases": {10: "A1", 9: "A2", 8: "B1", 7: "B2", 6: "C1", 5: "C2", 4: "D", 3: "E1", 2: "E1", 1: "E2", 0: "E2"},
    },
    "german_1_6": {
        "registry_code": "GERMAN_1_6",
        "score_scale": 6,
        # INVERTED: 1 (sehr gut) best … 6 (ungenügend) worst. Standard average-rounding
        # bands: 1 ≤1.49, 2 ≤2.49, 3 ≤3.49, 4 ≤4.49, 5 ≤5.49, 6 ≤6.0.
        "cases": {1.0: "1", 1.4: "1", 1.5: "2", 2.0: "2", 2.5: "3", 3.4: "3", 4.0: "4", 4.5: "5", 5.5: "6", 6.0: "6"},
    },
}


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


class InternationalBandResolutionTests(SimpleTestCase):
    """Parametrized score -> expected band label for each newly-computable scale."""

    def test_resolve_extended_band_label_cases(self):
        for scale, spec in _TARGET_SCALES.items():
            for score, expected in spec["cases"].items():
                self.assertEqual(
                    resolve_extended_band_label(scale, score),
                    expected,
                    msg=f"{scale} score={score}",
                )

    def test_format_grade_band_renders_rich_label(self):
        # The public display helper must surface the rich band, not a coarse A–E letter.
        self.assertEqual(format_grade_band("uk_gcse_9_1", 6), "6")
        self.assertEqual(format_grade_band("ib_1_7", 5), "5")
        self.assertEqual(format_grade_band("cbse_10", 9), "A2")
        self.assertEqual(format_grade_band("german_1_6", 2.0), "2")

    def test_converter_band_label_matches_resolver(self):
        for scale, spec in _TARGET_SCALES.items():
            conv = GradeConverter(_StubWeights(scale))
            for score, expected in spec["cases"].items():
                self.assertEqual(
                    conv.band_label(Decimal(str(score))),
                    expected,
                    msg=f"{scale} via GradeConverter score={score}",
                )


class GermanInvertedDirectionTests(SimpleTestCase):
    """German 1–6 is the only inverted family — lock that a lower score is a BETTER grade."""

    def test_lower_score_is_better_grade(self):
        # 1.0 (best) must NOT resolve to "6"; 6.0 (worst) must NOT resolve to "1".
        self.assertEqual(resolve_extended_band_label("german_1_6", 1.0), "1")
        self.assertEqual(resolve_extended_band_label("german_1_6", 6.0), "6")
        # Monotonic: as the score rises, the grade label rises (worsens) too.
        labels = [resolve_extended_band_label("german_1_6", s) for s in (1, 2, 3, 4, 5, 6)]
        self.assertEqual(labels, ["1", "2", "3", "4", "5", "6"])

    def test_out_of_range_clamps_to_boundary_band(self):
        # Below the best ceiling -> best grade; above the worst ceiling -> worst grade.
        self.assertEqual(resolve_extended_band_label("german_1_6", 0), "1")
        self.assertEqual(resolve_extended_band_label("german_1_6", 99), "6")

    def test_direction_flag_present_only_for_german(self):
        self.assertEqual(EXTENDED_GRADE_BANDS["german_1_6"].get("direction"), "ascending")
        for scale in ("uk_gcse_9_1", "ib_1_7", "cbse_10"):
            self.assertNotEqual(
                EXTENDED_GRADE_BANDS[scale].get("direction"), "ascending", msg=scale
            )


class InternationalScaleWiringTests(SimpleTestCase):
    """Each target scale is registered everywhere the operational↔catalog contract needs."""

    def test_registered_in_every_layer(self):
        valid_scale_type_values = set(GradingScale.ScaleType.values)
        for scale, spec in _TARGET_SCALES.items():
            self.assertIn(scale, _VALID_SCALE_TYPES, msg=scale)
            self.assertIn(scale, GRADING_SCALE_BANDS, msg=scale)
            self.assertIn(scale, EXTENDED_GRADE_BANDS, msg=scale)
            self.assertIn(scale, ASSESSMENT_WEIGHTS_SCALE_MAP, msg=scale)
            self.assertIn(scale, valid_scale_type_values, msg=scale)
            # The registry code resolves through the catalog↔engine bridge to THIS scale.
            self.assertEqual(REGISTRY_SCALE_TYPE_MAP[spec["registry_code"]], scale, msg=scale)

    def test_score_scale_matches_axis(self):
        for scale, spec in _TARGET_SCALES.items():
            self.assertEqual(
                EXTENDED_GRADE_BANDS[scale]["score_scale"], spec["score_scale"], msg=scale
            )
            self.assertEqual(
                GRADING_SCALE_BANDS[scale]["score_scale"], spec["score_scale"], msg=scale
            )

    def test_normalizer_and_wizard_accept_hyphen_and_canonical(self):
        # _normalize_scale_type does .replace("-", "_"), so the dashed form resolves too.
        self.assertEqual(_normalize_scale_type("uk_gcse_9_1"), "uk_gcse_9_1")
        self.assertEqual(_normalize_scale_type("german-1-6"), "german_1_6")
        self.assertEqual(_normalize_scale_type("cbse_10"), "cbse_10")
        self.assertEqual(_normalize_scale_type("ib_1_7"), "ib_1_7")
        # Whatever the wizard map knows for these must round-trip to the canonical type.
        for raw in ("uk_gcse_9_1", "ib_1_7", "german_1_6", "cbse_10"):
            mapped = _SCALE_TYPE_MAP.get(raw)
            if mapped is not None:  # wizard alias is optional; if present it must be correct
                self.assertEqual(mapped, raw, msg=raw)


class BandFamiliesUnchangedRegressionTests(SimpleTestCase):
    """The pre-existing extended families must be byte-for-byte unperturbed."""

    def test_waec_pass_fail_qualitative_unchanged(self):
        self.assertEqual(resolve_extended_band_label("waec_letter", 72), "B2")
        self.assertEqual(resolve_extended_band_label("waec_letter", 0), "F9")
        self.assertEqual(resolve_extended_band_label("pass_fail", 50), "Pass")
        self.assertEqual(resolve_extended_band_label("pass_fail", 49), "Fail")
        self.assertEqual(resolve_extended_band_label("qualitative_pd", 90), "Exceeding Expectations")
        self.assertEqual(resolve_extended_band_label("qualitative_pd", 30), "Beginning")

    def test_ordinary_scales_still_return_none(self):
        for scale in ("numeric_0_20", "letter_a_e", "gpa_4_0", "percentage", "numeric_1_5"):
            self.assertIsNone(resolve_extended_band_label(scale, 15), msg=scale)
