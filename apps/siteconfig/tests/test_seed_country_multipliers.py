"""CountryMultiplier PPP seed command + migration contract."""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.country_multiplier_seed import (
    COUNTRY_MULTIPLIER_SEED_ROWS,
    seed_country_multipliers,
)
from apps.siteconfig.models_platform_catalog import CountryMultiplier


class SeedCountryMultipliersTests(TestCase):
    def setUp(self):
        CountryMultiplier.objects.all().delete()

    def test_seed_creates_curated_rows(self):
        summary = seed_country_multipliers()
        self.assertGreater(summary["created"], 0)
        india = CountryMultiplier.objects.get(country_code="IN")
        self.assertEqual(india.multiplier, Decimal("0.2800"))
        self.assertEqual(india.tax_code, "GST")
        self.assertTrue(india.is_active)

    def test_seed_is_idempotent(self):
        seed_country_multipliers()
        second = seed_country_multipliers()
        self.assertEqual(second["created"], 0)
        self.assertGreaterEqual(second["updated"], len(COUNTRY_MULTIPLIER_SEED_ROWS))

    def test_management_command_single_country(self):
        call_command("seed_country_multipliers", country=["NG"])
        self.assertTrue(CountryMultiplier.objects.filter(country_code="NG").exists())
        self.assertFalse(CountryMultiplier.objects.filter(country_code="IN").exists())
