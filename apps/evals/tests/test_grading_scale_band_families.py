"""Phase B of the world-scale bridge: scales whose grade label does NOT fit the
5-band A–E model — WAEC (A1…F9), Pass/Fail, and qualitative descriptors.

Their rich label is DERIVED from EXTENDED_GRADE_BANDS (no schema change to the hot
Evaluation table). These no-DB tests prove each family resolves its true label, that
GradeConverter.band_label stays exactly numeric_to_letter for the ordinary scales
(backward-compatible), and that the public display helper renders the right label.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.evals.grading import (
    ASSESSMENT_WEIGHTS_SCALE_MAP,
    format_grade_band,
)
from apps.evals.grading_provisioning import _VALID_SCALE_TYPES, _normalize_scale_type
from apps.evals.grading_wizard_kernel import _SCALE_TYPE_MAP
from apps.evals.models import (
    EXTENDED_GRADE_BANDS,
    GRADING_SCALE_BANDS,
    resolve_extended_band_label,
)
from apps.evals.validators import GradeConverter


class _StubWeights:
    def __init__(self, scale_type: str):
        bands = GRADING_SCALE_BANDS[scale_type]
        self.grading_scale = scale_type
        self.score_scale = bands["score_scale"]
        self.grade_a_min = bands["a"]
        self.grade_b_min = bands["b"]
        self.grade_c_min = bands["c"]
        self.grade_d_min = bands["d"]
        self.grade_e_min = bands["e"]


class WaecBandTests(SimpleTestCase):
    def test_waec_band_boundaries(self):
        cases = {75: "A1", 72: "B2", 70: "B2", 64: "C4", 50: "C6", 49: "D7", 44: "E8", 39: "F9", 0: "F9"}
        for score, expected in cases.items():
            self.assertEqual(resolve_extended_band_label("waec_letter", score), expected, msg=score)

    def test_converter_band_label_and_convert(self):
        conv = GradeConverter(_StubWeights("waec_letter"))
        self.assertEqual(conv.band_label(Decimal("72")), "B2")
        out = conv.convert(Decimal("72"))
        self.assertEqual(out["band"], "B2")          # rich label
        self.assertEqual(out["letter"], "B")          # coarse A–E tier still computed


class PassFailTests(SimpleTestCase):
    def test_binary_boundaries(self):
        self.assertEqual(resolve_extended_band_label("pass_fail", 50), "Pass")
        self.assertEqual(resolve_extended_band_label("pass_fail", 100), "Pass")
        self.assertEqual(resolve_extended_band_label("pass_fail", 49), "Fail")
        self.assertEqual(resolve_extended_band_label("pass_fail", 0), "Fail")


class QualitativeTests(SimpleTestCase):
    def test_descriptor_boundaries(self):
        self.assertEqual(resolve_extended_band_label("qualitative_pd", 90), "Exceeding Expectations")
        self.assertEqual(resolve_extended_band_label("qualitative_pd", 70), "Meeting Expectations")
        self.assertEqual(resolve_extended_band_label("qualitative_pd", 50), "Approaching Expectations")
        self.assertEqual(resolve_extended_band_label("qualitative_pd", 30), "Beginning")


class FrenchMentionTests(SimpleTestCase):
    def test_note_sur_20_mentions(self):
        cases = {
            18: "Très bien", 16: "Très bien", 15: "Bien", 14: "Bien",
            13: "Assez bien", 12: "Assez bien", 11: "Passable", 10: "Passable",
            9: "Insuffisant", 0: "Insuffisant",
        }
        for score, expected in cases.items():
            self.assertEqual(
                resolve_extended_band_label("french_0_20", score), expected, msg=score
            )

    def test_converter_band_label_uses_mention(self):
        conv = GradeConverter(_StubWeights("french_0_20"))
        self.assertEqual(conv.band_label(Decimal("18")), "Très bien")
        self.assertEqual(conv.convert(Decimal("18"))["band"], "Très bien")

    def test_anglophone_numeric_0_20_still_letters(self):
        # Only the francophone key maps to mentions; anglophone 0–20 keeps A–E.
        self.assertIsNone(resolve_extended_band_label("numeric_0_20", 18))
        conv = GradeConverter(_StubWeights("numeric_0_20"))
        self.assertEqual(
            conv.band_label(Decimal("18")), conv.numeric_to_letter(Decimal("18"))
        )


class BackwardCompatTests(SimpleTestCase):
    def test_extended_resolver_returns_none_for_five_band_scales(self):
        # The A–E numeric scales are NOT extended families — resolver returns None so
        # callers fall back to numeric_to_letter. (Lock this: a regression here would
        # silently reroute every ordinary grade.)
        for scale in ("numeric_0_20", "letter_a_e", "gpa_4_0", "percentage", "numeric_1_5"):
            self.assertIsNone(resolve_extended_band_label(scale, 15), msg=scale)

    def test_band_label_equals_letter_for_ordinary_scales(self):
        for scale in ("numeric_0_20", "percentage"):
            conv = GradeConverter(_StubWeights(scale))
            score = Decimal("18") if scale == "numeric_0_20" else Decimal("90")
            self.assertEqual(conv.band_label(score), conv.numeric_to_letter(score), msg=scale)
            self.assertEqual(conv.convert(score)["band"], conv.convert(score)["letter"], msg=scale)

    def test_none_score_safe(self):
        self.assertIsNone(resolve_extended_band_label("waec_letter", None))
        self.assertEqual(GradeConverter(_StubWeights("waec_letter")).band_label(None), "")


class DisplayHelperAndWiringTests(SimpleTestCase):
    def test_format_grade_band(self):
        self.assertEqual(format_grade_band("waec_letter", 72), "B2")
        self.assertEqual(format_grade_band("pass_fail", 50), "Pass")
        self.assertEqual(format_grade_band("qualitative_pd", 70), "Meeting Expectations")
        self.assertEqual(format_grade_band("numeric_0_20", 18), "A")  # ordinary A–E letter
        self.assertEqual(format_grade_band("anything", None), "")

    def test_families_registered_everywhere(self):
        for scale in ("waec_letter", "pass_fail", "qualitative_pd"):
            self.assertIn(scale, _VALID_SCALE_TYPES, msg=scale)
            self.assertIn(scale, GRADING_SCALE_BANDS, msg=scale)
            self.assertIn(scale, EXTENDED_GRADE_BANDS, msg=scale)
            self.assertEqual(ASSESSMENT_WEIGHTS_SCALE_MAP[scale], "0-100", msg=scale)
        self.assertEqual(_normalize_scale_type("waec"), "waec_letter")
        self.assertEqual(_SCALE_TYPE_MAP["binary"], "pass_fail")
        self.assertEqual(_SCALE_TYPE_MAP["qualitative"], "qualitative_pd")

    def test_score_scale_is_100_for_band_families(self):
        for scale in ("waec_letter", "pass_fail", "qualitative_pd"):
            self.assertEqual(GRADING_SCALE_BANDS[scale]["score_scale"], 100, msg=scale)
