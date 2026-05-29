"""v4.00.36 — end-to-end trace: Plan + tenant country → localized price.

Demonstrates the audit-claimed integration: a tenant in country X being
quoted Plan(base_price=100 USD) actually delivers a price in X's local
currency with PPP scaling and VAT applied.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase

from apps.billing.services import compute_subscription_price_for_school


class ComputeSubscriptionPriceIntegrationTests(SimpleTestCase):
    """Pure-mock integration trace; no DB."""

    def _mock_country_row(self, multiplier="1.0", tax_rate="0.0", tax_code=""):
        row = mock.Mock()
        row.multiplier = Decimal(multiplier)
        row.tax_rate = Decimal(tax_rate)
        row.tax_code = tax_code
        return row

    def test_none_school_returns_zero_envelope(self):
        result = compute_subscription_price_for_school(None, mock.Mock())
        self.assertEqual(result["total"], Decimal("0.00"))
        self.assertEqual(result["currency_code"], "USD")

    def test_none_plan_returns_zero_envelope(self):
        result = compute_subscription_price_for_school(mock.Mock(), None)
        self.assertEqual(result["total"], Decimal("0.00"))

    def test_flat_plan_in_nigeria_with_vat(self):
        # Nigeria: 75% of base + 7.5% VAT, NGN currency.
        school = mock.Mock(country_code="NG")
        plan = mock.Mock()
        plan.billing_model = "FLAT"
        plan.base_price = Decimal("100.00")
        plan.price_per_student = None
        plan.tier_rules = {}

        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row",
            return_value=self._mock_country_row(
                multiplier="0.7500", tax_rate="0.0750", tax_code="VAT"
            ),
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_currency_for_country",
            return_value="NGN",
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_tax_rate",
            return_value=Decimal("0.075"),
        ):
            result = compute_subscription_price_for_school(school, plan)

        self.assertEqual(result["currency_code"], "NGN")
        self.assertEqual(result["subtotal"], Decimal("75.00"))  # 100 × 0.75
        self.assertEqual(result["tax"], Decimal("5.63"))  # 75 × 0.075 HALF_UP
        self.assertEqual(result["total"], Decimal("80.63"))
        self.assertEqual(result["multiplier"], Decimal("0.7500"))
        self.assertEqual(result["country_code"], "NG")
        self.assertEqual(result["billing_model"], "FLAT")

    def test_per_student_plan_in_india(self):
        # India: 28% scale + 18% GST, INR currency, 200 students.
        school = mock.Mock(country_code="IN")
        plan = mock.Mock()
        plan.billing_model = "PER_STUDENT"
        plan.price_per_student = Decimal("2.00")
        plan.base_price = None
        plan.tier_rules = {}

        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row",
            return_value=self._mock_country_row(multiplier="0.2800"),
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_currency_for_country",
            return_value="INR",
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_tax_rate",
            return_value=Decimal("0.18"),
        ):
            result = compute_subscription_price_for_school(school, plan, student_count=200)

        # base_price = 2.00 × 200 = 400 USD
        # subtotal = 400 × 0.28 = 112.00 INR equivalent
        # tax = 112.00 × 0.18 = 20.16
        self.assertEqual(result["subtotal"], Decimal("112.00"))
        self.assertEqual(result["tax"], Decimal("20.16"))
        self.assertEqual(result["total"], Decimal("132.16"))
        self.assertEqual(result["currency_code"], "INR")

    def test_tiered_plan_first_band(self):
        school = mock.Mock(country_code="US")
        plan = mock.Mock()
        plan.billing_model = "TIERED"
        plan.base_price = None
        plan.price_per_student = None
        plan.tier_rules = [
            {"max": 500, "price": 200},
            {"max": 2000, "price": 600},
        ]

        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row",
            return_value=self._mock_country_row(multiplier="1.0"),
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_currency_for_country",
            return_value="USD",
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_tax_rate",
            return_value=Decimal("0"),
        ):
            result = compute_subscription_price_for_school(school, plan, student_count=100)

        self.assertEqual(result["subtotal"], Decimal("200.00"))
        self.assertEqual(result["billing_model"], "TIERED")

    def test_missing_country_row_falls_back_to_base_usd(self):
        school = mock.Mock(country_code="ZZ")
        plan = mock.Mock()
        plan.billing_model = "FLAT"
        plan.base_price = Decimal("50.00")
        plan.price_per_student = None
        plan.tier_rules = {}

        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row", return_value=None
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_currency_for_country",
            return_value="USD",
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_tax_rate",
            return_value=Decimal("0"),
        ):
            result = compute_subscription_price_for_school(school, plan)

        # Missing country row → multiplier=1, tax=0, currency=USD.
        self.assertEqual(result["subtotal"], Decimal("50.00"))
        self.assertEqual(result["tax"], Decimal("0.00"))
        self.assertEqual(result["total"], Decimal("50.00"))
        self.assertEqual(result["currency_code"], "USD")
