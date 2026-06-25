"""`_auto_teacher_remark` must band on the SCHOOL'S grade scale, not a fixed /20.

A /100 school's 80 average and a /20 school's 16 average are BOTH "Excellent"
(0.80 normalized) — the report-card remark must read the same band on any scale.
Pure no-DB tests: `score_to_normalized` is mocked / driven via the /20 default.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.reports.services import _auto_teacher_remark


class AutoTeacherRemarkScaleAwareTests(SimpleTestCase):
    def test_none_average_is_pending(self):
        self.assertEqual(_auto_teacher_remark(None), "Pending results.")

    @patch("apps.evals.grading.score_to_normalized")
    def test_bands_follow_normalized_value_any_scale(self, mock_norm):
        cases = [
            (0.95, "Excellent performance."),
            (0.80, "Excellent performance."),
            (0.79, "Very good work."),
            (0.70, "Very good work."),
            (0.60, "Good progress."),
            (0.50, "Satisfactory performance."),
            (0.40, "Needs improvement."),
            (0.20, "Unsatisfactory performance."),
        ]
        for norm, expected in cases:
            mock_norm.return_value = norm
            self.assertEqual(
                _auto_teacher_remark(50, school=object()), expected, f"norm={norm}"
            )

    @patch("apps.evals.grading.score_to_normalized")
    def test_percentage_school_80_is_excellent(self, mock_norm):
        # A /100 school: 80/100 → 0.80 normalized → Excellent (was "Unsatisfactory"
        # under the old hardcoded /20 bands because 80 < 16 is false but the bands
        # only knew /20 — the bug this fix closes).
        mock_norm.return_value = 0.80
        self.assertEqual(
            _auto_teacher_remark(80, school=object()), "Excellent performance."
        )

    def test_legacy_20_preserved_via_default_scale(self):
        # No school → score_to_normalized falls back to the /20 default, so the
        # historical francophone behaviour (16→Excellent, 10→Satisfactory) holds.
        self.assertEqual(_auto_teacher_remark(16, school=None), "Excellent performance.")
        self.assertEqual(
            _auto_teacher_remark(10, school=None), "Satisfactory performance."
        )
        self.assertEqual(
            _auto_teacher_remark(5, school=None), "Unsatisfactory performance."
        )

    def test_degrades_to_20_basis_when_normalizer_raises(self):
        with patch("apps.evals.grading.score_to_normalized", side_effect=ValueError):
            self.assertEqual(
                _auto_teacher_remark(16, school=None), "Excellent performance."
            )
            self.assertEqual(
                _auto_teacher_remark(8, school=None), "Needs improvement."
            )
