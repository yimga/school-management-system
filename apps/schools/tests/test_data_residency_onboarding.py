"""Tests for data_residency_onboarding (batch 1530)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.schools.data_residency_onboarding import apply_data_residency_for_new_school


class DataResidencyOnboardingTests(SimpleTestCase):
    @patch(
        "apps.schools.data_residency_onboarding.derive_default_region",
        return_value="eu_central",
    )
    def test_apply_sets_region_from_country(self, _mock_derive):
        school = SimpleNamespace(
            country_code="DE",
            data_region="",
            settings={},
            pk=1,
            slug="test-school",
        )
        out = apply_data_residency_for_new_school(school, source="test")
        self.assertEqual(school.data_region, "eu_central")
        self.assertEqual(out["data_region"], "eu_central")
        self.assertIn("data_residency", school.settings)
