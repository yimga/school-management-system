"""OCR marksheet score validation is local-first: scores are checked against the
school's grading-scale max, not a hardcoded 0-20 that rejected valid percentage /
GPA scores for US / UK / Nigerian schools.
"""

from decimal import Decimal

from django.test import SimpleTestCase

from apps.evals.views import _validate_ocr_entries


def _entry(value):
    return {"student_code": "S1", "scores": {"seq1": value}}


class ValidateOcrEntriesTests(SimpleTestCase):
    def test_default_max_is_twenty_back_compat(self):
        self.assertEqual(_validate_ocr_entries([_entry("18")]), [])
        errs = _validate_ocr_entries([_entry("21")])
        self.assertEqual(len(errs), 1)
        self.assertIn("0 to 20", errs[0])

    def test_percentage_scale_accepts_scores_above_twenty(self):
        # A US / Nigerian percentage school: 85 is valid, not rejected as > 20.
        self.assertEqual(_validate_ocr_entries([_entry("85")], Decimal("100")), [])
        self.assertEqual(_validate_ocr_entries([_entry("100")], Decimal("100")), [])
        errs = _validate_ocr_entries([_entry("101")], Decimal("100"))
        self.assertEqual(len(errs), 1)
        self.assertIn("0 to 100", errs[0])

    def test_gpa_scale_rejects_above_four(self):
        self.assertEqual(_validate_ocr_entries([_entry("3.7")], Decimal("4")), [])
        errs = _validate_ocr_entries([_entry("4.5")], Decimal("4"))
        self.assertEqual(len(errs), 1)
        self.assertIn("0 to 4", errs[0])

    def test_negative_and_non_numeric_still_flagged(self):
        self.assertIn("0 to 20", _validate_ocr_entries([_entry("-1")])[0])
        self.assertIn("invalid number", _validate_ocr_entries([_entry("abc")])[0])

    def test_label_is_clean_for_integral_and_fractional_maxes(self):
        # Integral max -> no spurious decimals; the rstrip never corrupts "100".
        self.assertIn("0 to 100", _validate_ocr_entries([_entry("999")], Decimal("100"))[0])
        self.assertIn("0 to 10", _validate_ocr_entries([_entry("999")], Decimal("10"))[0])
        self.assertIn("0 to 7.5", _validate_ocr_entries([_entry("999")], Decimal("7.5"))[0])

    def test_bad_max_score_falls_back_to_twenty(self):
        errs = _validate_ocr_entries([_entry("50")], "not-a-number")
        self.assertIn("0 to 20", errs[0])
