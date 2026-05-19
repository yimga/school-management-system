"""Glocal grading: scale-aware validation and scale id normalization."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from apps.evals.grading import (
    GRADING_SCALES,
    get_scale_for_school,
    max_score_for_school,
    normalize_scale_id,
)


class GlocalGradingSovereigntyTests(TestCase):
    def test_normalize_assessment_weights_scale(self):
        self.assertEqual(normalize_scale_id("numeric_0_20"), "0-20")
        self.assertEqual(normalize_scale_id("percentage"), "0-100")
        self.assertEqual(normalize_scale_id("gpa_4_0"), "gpa")
        self.assertEqual(normalize_scale_id("uk_honours"), "uk-honours")
        self.assertEqual(normalize_scale_id("ib_0_7"), "ib-7")

    def test_max_score_for_us_school(self):
        school = SimpleNamespace()
        from unittest.mock import patch

        with patch(
            "apps.siteconfig.tenant_config.get_grading_schema_for_school",
            return_value={"scale": "0-100"},
        ):
            self.assertEqual(max_score_for_school(school), Decimal("100"))

    def test_max_score_for_cameroon_school(self):
        school = SimpleNamespace()
        from unittest.mock import patch

        with patch(
            "apps.siteconfig.tenant_config.get_grading_schema_for_school",
            return_value={"scale": "0-20"},
        ):
            self.assertEqual(max_score_for_school(school), Decimal("20"))

    def test_get_scale_for_school_normalizes_alias(self):
        school = SimpleNamespace()
        from unittest.mock import patch

        with patch(
            "apps.siteconfig.tenant_config.get_grading_schema_for_school",
            return_value={"scale": "numeric_0_20"},
        ):
            self.assertEqual(get_scale_for_school(school), "0-20")
            self.assertIn(get_scale_for_school(school), GRADING_SCALES)
