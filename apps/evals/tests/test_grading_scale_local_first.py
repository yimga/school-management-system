"""Wave 4 — grading is scale-driven, not Cameroon-locked.

Two fixes, both backward-compatible with the legacy numeric_0_20 (0–20) default:

  1. A new AssessmentWeights row created with a NON-default grading_scale and untouched
     thresholds is realigned to that scale's bands (percentage → 80/70/60/50, GPA → its
     bands) instead of always using Cameroon's 0–20 thresholds. Explicit thresholds and
     the numeric_0_20 default are never changed.
  2. GradeConverter GPA/percentage conversion uses the configured score_scale, not a
     hardcoded /20 — so percentage (100) and GPA (4) schools convert correctly.

All SimpleTestCase — fake instances, no DB.
"""

from types import SimpleNamespace

from django.test import SimpleTestCase


class _State:
    def __init__(self, adding):
        self.adding = adding


def _weights(scale="numeric_0_20", adding=True, bands=(18.0, 16.0, 14.0, 10.0, 0.0), score_scale=20):
    return SimpleNamespace(
        _state=_State(adding),
        grading_scale=scale,
        grade_a_min=bands[0],
        grade_b_min=bands[1],
        grade_c_min=bands[2],
        grade_d_min=bands[3],
        grade_e_min=bands[4],
        score_scale=score_scale,
    )


class GradingScaleBandsTests(SimpleTestCase):
    def test_band_registry_per_scale(self):
        from apps.evals.models import default_bands_for_scale

        pct = default_bands_for_scale("percentage")
        self.assertEqual((pct["a"], pct["b"], pct["c"], pct["d"]), (80, 70, 60, 50))
        self.assertEqual(pct["score_scale"], 100)
        gpa = default_bands_for_scale("gpa_4_0")
        self.assertEqual(gpa["score_scale"], 4)

    def test_unknown_scale_defaults_numeric_0_20(self):
        from apps.evals.models import default_bands_for_scale

        self.assertEqual(default_bands_for_scale("nope")["score_scale"], 20)


class ScaleConsistentBandsTests(SimpleTestCase):
    def _apply(self, w):
        from apps.evals.models import _apply_scale_consistent_bands

        _apply_scale_consistent_bands(w)
        return w

    def test_percentage_scale_realigns_default_thresholds(self):
        w = self._apply(_weights(scale="percentage"))
        self.assertEqual(int(w.grade_a_min), 80)
        self.assertEqual(int(w.grade_c_min), 60)
        self.assertEqual(int(w.score_scale), 100)

    def test_numeric_0_20_default_untouched(self):
        w = self._apply(_weights(scale="numeric_0_20"))
        self.assertEqual(float(w.grade_a_min), 18.0)
        self.assertEqual(int(w.score_scale), 20)

    def test_explicit_thresholds_preserved(self):
        # Non-default scale but caller set custom thresholds → not overwritten.
        w = self._apply(_weights(scale="percentage", bands=(90.0, 80.0, 70.0, 60.0, 0.0)))
        self.assertEqual(int(w.grade_a_min), 90)

    def test_noop_on_update(self):
        w = self._apply(_weights(scale="percentage", adding=False))
        self.assertEqual(float(w.grade_a_min), 18.0)


class GpaScaleConversionTests(SimpleTestCase):
    def _conv(self, score_scale):
        from apps.evals.validators import GradeConverter

        return GradeConverter(SimpleNamespace(score_scale=score_scale))

    def test_gpa_uses_score_scale(self):
        # 0–20 default: 20 → 4.0 GPA. Percentage: 100 score, scale 100 → 4.0 GPA.
        self.assertAlmostEqual(self._conv(20).numeric_to_gpa(20), 4.0)
        self.assertAlmostEqual(self._conv(100).numeric_to_gpa(100), 4.0)
        self.assertAlmostEqual(self._conv(100).numeric_to_gpa(50), 2.0)

    def test_percentage_uses_score_scale(self):
        self.assertAlmostEqual(self._conv(20).numeric_to_percentage(10), 50.0)
        self.assertAlmostEqual(self._conv(100).numeric_to_percentage(73), 73.0)

    def test_zero_or_bad_scale_degrades_to_20(self):
        self.assertAlmostEqual(self._conv(0).numeric_to_gpa(20), 4.0)
