"""CountryMultiplier PPP seed command + migration contract."""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.country_multiplier_seed import (
    COUNTRY_MULTIPLIER_SEED_ROWS,
    all_catalog_country_codes,
    expand_seed_to_all_countries,
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
        japan = CountryMultiplier.objects.get(country_code="JP")
        self.assertEqual(japan.multiplier, Decimal("0.8800"))
        self.assertGreaterEqual(len(COUNTRY_MULTIPLIER_SEED_ROWS), 45)

    def test_seed_is_idempotent(self):
        seed_country_multipliers()
        second = seed_country_multipliers()
        self.assertEqual(second["created"], 0)
        self.assertGreaterEqual(second["updated"], len(COUNTRY_MULTIPLIER_SEED_ROWS))

    def test_management_command_single_country(self):
        call_command("seed_country_multipliers", country=["NG"])
        self.assertTrue(CountryMultiplier.objects.filter(country_code="NG").exists())
        self.assertFalse(CountryMultiplier.objects.filter(country_code="IN").exists())

    def test_expand_seed_backfills_neutral_defaults(self):
        summary = expand_seed_to_all_countries()
        catalog_n = len(all_catalog_country_codes())
        self.assertGreaterEqual(CountryMultiplier.objects.count(), catalog_n)
        self.assertGreaterEqual(summary.get("backfilled_default", 0), 0)
        curated_codes = {r["country_code"] for r in COUNTRY_MULTIPLIER_SEED_ROWS}
        # Pick a catalog code that is not curated — must be neutral 1.0× Zone B.
        neutral = next(
            (c for c in all_catalog_country_codes() if c not in curated_codes),
            None,
        )
        self.assertIsNotNone(neutral)
        row = CountryMultiplier.objects.get(country_code=neutral)
        self.assertEqual(row.multiplier, Decimal("1.0000"))
        self.assertEqual(row.zone, "B")
        nigeria = CountryMultiplier.objects.get(country_code="NG")
        self.assertEqual(nigeria.multiplier, Decimal("0.3500"))

    def test_management_command_all_catalog(self):
        call_command("seed_country_multipliers", all_catalog=True)
        self.assertGreaterEqual(
            CountryMultiplier.objects.count(), len(COUNTRY_MULTIPLIER_SEED_ROWS)
        )
