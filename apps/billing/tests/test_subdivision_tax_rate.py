"""Subdivision-level tax rates (B3).

CountryMultiplier.tax_rate is one coarse rate per country, but sales/consumption
tax varies below the country (US state, CA province, ...). SubdivisionTaxRate
holds those finer rates and the static resolver consults them when a
subdivision_code is supplied, falling back to the country rate — so adding rows
only ADDS specificity and never changes the country-level default. All rates are
Decimal end-to-end (no float).
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.billing import tax_engine
from apps.siteconfig.models_platform_catalog import CountryMultiplier, SubdivisionTaxRate


class SubdivisionTaxRateResolverTests(TestCase):
    def setUp(self):
        # Default active resolver may have been changed by other tests; pin it.
        tax_engine.set_active_resolver("static")
        # US has no federal sales tax (country 0); California adds 7.25%.
        CountryMultiplier.objects.create(
            country_code="US", tax_rate=Decimal("0.0000"), is_active=True
        )
        SubdivisionTaxRate.objects.create(
            country_code="US",
            subdivision_code="CA",
            tax_rate=Decimal("0.0725"),
            is_active=True,
        )

    def test_country_rate_used_without_subdivision(self):
        CountryMultiplier.objects.filter(country_code="US").update(
            tax_rate=Decimal("0.0600")
        )
        self.assertEqual(tax_engine.static_tax_resolver("US"), Decimal("0.0600"))

    def test_subdivision_rate_overrides_country(self):
        rate = tax_engine.static_tax_resolver("US", subdivision_code="CA")
        self.assertIsInstance(rate, Decimal)
        self.assertEqual(rate, Decimal("0.0725"))

    def test_unknown_subdivision_falls_back_to_country(self):
        CountryMultiplier.objects.filter(country_code="US").update(
            tax_rate=Decimal("0.0500")
        )
        self.assertEqual(
            tax_engine.static_tax_resolver("US", subdivision_code="ZZ"),
            Decimal("0.0500"),
        )

    def test_inactive_subdivision_row_ignored(self):
        SubdivisionTaxRate.objects.filter(
            country_code="US", subdivision_code="CA"
        ).update(is_active=False)
        CountryMultiplier.objects.filter(country_code="US").update(
            tax_rate=Decimal("0.0300")
        )
        self.assertEqual(
            tax_engine.static_tax_resolver("US", subdivision_code="CA"),
            Decimal("0.0300"),
        )

    def test_country_and_subdivision_match_case_insensitively(self):
        self.assertEqual(
            tax_engine.static_tax_resolver("us", subdivision_code="ca"),
            Decimal("0.0725"),
        )

    def test_resolve_tax_rate_returns_subdivision_decimal(self):
        rate = tax_engine.resolve_tax_rate("US", subdivision_code="CA")
        self.assertIsInstance(rate, Decimal)
        self.assertEqual(rate, Decimal("0.0725"))

    def test_resolve_tax_rate_never_returns_none(self):
        rate = tax_engine.resolve_tax_rate("ZZ", subdivision_code="ZZ")
        self.assertIsInstance(rate, Decimal)
        self.assertEqual(rate, Decimal("0"))

    def test_subdivision_helper_guards_empty_inputs(self):
        self.assertIsNone(tax_engine._subdivision_tax_rate("", "CA"))
        self.assertIsNone(tax_engine._subdivision_tax_rate("US", ""))

    def test_no_country_returns_none(self):
        self.assertIsNone(tax_engine.static_tax_resolver(""))

    def test_unique_together_country_subdivision(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SubdivisionTaxRate.objects.create(
                    country_code="US",
                    subdivision_code="CA",
                    tax_rate=Decimal("0.0900"),
                )
