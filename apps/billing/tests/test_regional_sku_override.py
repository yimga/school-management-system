"""Per-country Plan SKU overrides (B2).

A Plan can carry ``regional_sku_overrides`` keyed by ISO country code. When a
tenant's country has an override, that explicit amount becomes the localized
subtotal directly, bypassing the PPP multiplier so one market can be repriced
without changing the global formula. Tax still applies on top. Decimal
throughout.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.billing.regional_pricing import compute_localized_price
from apps.billing.services import compute_subscription_price_for_school
from apps.siteconfig.models_platform_catalog import CountryMultiplier, Plan


class PlanRegionalSkuOverrideResolverTests(TestCase):
    def test_override_lookup_by_upper_and_as_given(self):
        plan = Plan(regional_sku_overrides={"NG": "15000", "in": "999"})
        self.assertEqual(plan.regional_sku_override_for("ng"), Decimal("15000"))
        self.assertEqual(plan.regional_sku_override_for("NG"), Decimal("15000"))
        # key stored lower-case is still found via the as-given fallback
        self.assertEqual(plan.regional_sku_override_for("in"), Decimal("999"))

    def test_override_absent_or_invalid_returns_none(self):
        self.assertIsNone(Plan(regional_sku_overrides={}).regional_sku_override_for("US"))
        self.assertIsNone(
            Plan(regional_sku_overrides={"US": ""}).regional_sku_override_for("US")
        )
        self.assertIsNone(
            Plan(regional_sku_overrides={"US": "abc"}).regional_sku_override_for("US")
        )
        self.assertIsNone(
            Plan(regional_sku_overrides={"US": "-5"}).regional_sku_override_for("US")
        )
        self.assertIsNone(
            Plan(regional_sku_overrides="not-a-dict").regional_sku_override_for("US")
        )
        self.assertIsNone(Plan(regional_sku_overrides={"US": "9"}).regional_sku_override_for(""))


class ComputeLocalizedPriceOverrideTests(TestCase):
    def setUp(self):
        # US: multiplier 2x, 10% tax — so a non-override price would be 200 + tax.
        CountryMultiplier.objects.create(
            country_code="US",
            multiplier=Decimal("2"),
            tax_rate=Decimal("0.1000"),
            is_active=True,
        )

    def test_override_bypasses_multiplier_but_keeps_tax(self):
        lp = compute_localized_price(Decimal("100"), "US", sku_override=Decimal("50"))
        self.assertTrue(lp.sku_override_applied)
        self.assertEqual(lp.subtotal, Decimal("50.00"))
        self.assertEqual(lp.multiplier, Decimal("1"))
        self.assertEqual(lp.tax, Decimal("5.00"))  # 50 * 10%
        self.assertEqual(lp.total, Decimal("55.00"))

    def test_no_override_uses_standard_multiplier_path(self):
        lp = compute_localized_price(Decimal("100"), "US")
        self.assertFalse(lp.sku_override_applied)
        self.assertEqual(lp.subtotal, Decimal("200.00"))  # 100 * 2
        self.assertEqual(lp.total, Decimal("220.00"))

    def test_zero_or_negative_override_is_ignored(self):
        lp = compute_localized_price(Decimal("100"), "US", sku_override=Decimal("0"))
        self.assertFalse(lp.sku_override_applied)
        self.assertEqual(lp.subtotal, Decimal("200.00"))


class SubscriptionPriceUsesOverrideTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        CountryMultiplier.objects.create(
            country_code="NG",
            multiplier=Decimal("0.5"),
            tax_rate=Decimal("0.0000"),
            is_active=True,
        )
        self.plan = Plan.objects.create(
            name="Pro",
            slug="pro-b2",
            base_price=Decimal("100.00"),
            is_active=True,
            regional_sku_overrides={"NG": "15000"},
        )
        self.school = School.objects.create(
            name="ng-school",
            slug="ng-school-b2",
            subdomain="ng-school-b2",
            is_active=True,
            country_code="NG",
            plan=self.plan,
        )

    def test_subscription_price_applies_country_override(self):
        priced = compute_subscription_price_for_school(self.school, self.plan)
        self.assertTrue(priced["sku_override_applied"])
        # 15000 explicit, NOT 100 * 0.5 = 50
        self.assertEqual(priced["subtotal"], Decimal("15000.00"))

    def test_subscription_price_without_override_uses_formula(self):
        self.plan.regional_sku_overrides = {}
        self.plan.save(update_fields=["regional_sku_overrides"])
        priced = compute_subscription_price_for_school(self.school, self.plan)
        self.assertFalse(priced["sku_override_applied"])
        self.assertEqual(priced["subtotal"], Decimal("50.00"))  # 100 * 0.5
