"""Unit tests for get_risk_band_for_school (Plan XVII risk thresholds)."""

from decimal import Decimal

from django.test import TestCase

from apps.analytics.models import RiskThresholds, get_risk_band_for_school
from apps.schools.models import School


class GetRiskBandForSchoolTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Band School",
            slug="band-school",
            subdomain="band-school",
            is_active=True,
        )

    def test_default_red(self):
        self.assertEqual(get_risk_band_for_school(80, self.school), "red")
        self.assertEqual(get_risk_band_for_school(100, self.school), "red")

    def test_default_amber(self):
        self.assertEqual(get_risk_band_for_school(50, self.school), "amber")
        self.assertEqual(get_risk_band_for_school(79, self.school), "amber")

    def test_default_green(self):
        self.assertEqual(get_risk_band_for_school(0, self.school), "green")
        self.assertEqual(get_risk_band_for_school(49, self.school), "green")

    def test_custom_thresholds_red(self):
        RiskThresholds.objects.create(
            school=self.school,
            amber_min=Decimal("40"),
            red_min=Decimal("70"),
        )
        self.assertEqual(get_risk_band_for_school(70, self.school), "red")
        self.assertEqual(get_risk_band_for_school(85, self.school), "red")

    def test_custom_thresholds_amber(self):
        RiskThresholds.objects.create(
            school=self.school,
            amber_min=Decimal("40"),
            red_min=Decimal("70"),
        )
        self.assertEqual(get_risk_band_for_school(40, self.school), "amber")
        self.assertEqual(get_risk_band_for_school(69, self.school), "amber")

    def test_custom_thresholds_green(self):
        RiskThresholds.objects.create(
            school=self.school,
            amber_min=Decimal("40"),
            red_min=Decimal("70"),
        )
        self.assertEqual(get_risk_band_for_school(0, self.school), "green")
        self.assertEqual(get_risk_band_for_school(39, self.school), "green")
