"""v4.00.36 — unit tests for apps.billing.regional_pricing."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase

from apps.billing.regional_pricing import LocalizedPrice, compute_localized_price


def _mock_row(multiplier="1.0000", tax_rate="0.0000", tax_code=""):
    row = mock.Mock()
    row.multiplier = Decimal(multiplier)
    row.tax_rate = Decimal(tax_rate)
    row.tax_code = tax_code
    return row


class ComputeLocalizedPricePureTests(SimpleTestCase):
    """No DB — mocks _resolve_country_row + static_tax_resolver."""

    def setUp(self):
        # Block any DB call the regional_pricing or tax_engine paths attempt.
        self._currency_patch = mock.patch(
            "apps.billing.regional_pricing._resolve_currency_for_country",
            return_value="USD",
        )
        self._tax_patch = mock.patch(
            "apps.billing.regional_pricing._resolve_tax_rate",
            return_value=Decimal("0"),
        )
        self._currency_patch.start()
        self._tax_patch.start()

    def tearDown(self):
        self._tax_patch.stop()
        self._currency_patch.stop()

    def test_missing_country_falls_back_to_base(self):
        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row", return_value=None
        ):
            result = compute_localized_price(Decimal("100.00"), "XX")
        self.assertIsInstance(result, LocalizedPrice)
        self.assertEqual(result.subtotal, Decimal("100.00"))
        self.assertEqual(result.tax, Decimal("0.00"))
        self.assertEqual(result.total, Decimal("100.00"))
        self.assertEqual(result.multiplier, Decimal("1"))
        self.assertEqual(result.tax_rate, Decimal("0"))
        self.assertEqual(result.currency_code, "USD")

    def test_ppp_scaling_applies(self):
        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row",
            return_value=_mock_row(multiplier="0.2800"),
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_currency_for_country",
            return_value="INR",
        ):
            result = compute_localized_price(Decimal("100.00"), "IN")
        self.assertEqual(result.subtotal, Decimal("28.00"))
        self.assertEqual(result.tax, Decimal("0.00"))
        self.assertEqual(result.total, Decimal("28.00"))
        self.assertEqual(result.currency_code, "INR")

    def test_vat_applies_after_ppp(self):
        # India: 28% scale + 18% GST — tax_engine path returns the row's rate.
        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row",
            return_value=_mock_row(
                multiplier="0.2800", tax_rate="0.1800", tax_code="GST"
            ),
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_currency_for_country",
            return_value="INR",
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_tax_rate",
            return_value=Decimal("0.18"),
        ):
            result = compute_localized_price(Decimal("100.00"), "IN")
        self.assertEqual(result.subtotal, Decimal("28.00"))
        # 28.00 * 0.18 = 5.04
        self.assertEqual(result.tax, Decimal("5.04"))
        self.assertEqual(result.total, Decimal("33.04"))
        self.assertEqual(result.tax_code, "GST")

    def test_currency_override_wins(self):
        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row", return_value=None
        ):
            result = compute_localized_price(
                Decimal("100.00"), "XX", currency_override="EUR"
            )
        self.assertEqual(result.currency_code, "EUR")

    def test_zero_base_yields_zero_total(self):
        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row",
            return_value=_mock_row(multiplier="0.5", tax_rate="0.2"),
        ), mock.patch(
            "apps.billing.regional_pricing._resolve_tax_rate",
            return_value=Decimal("0.2"),
        ):
            result = compute_localized_price(Decimal("0"), "XX")
        self.assertEqual(result.total, Decimal("0.00"))

    def test_decimal_rounding_half_up(self):
        # 99.99 * 0.3333 = 33.32666... → 33.33 (HALF_UP)
        with mock.patch(
            "apps.billing.regional_pricing._resolve_country_row",
            return_value=_mock_row(multiplier="0.3333"),
        ):
            result = compute_localized_price(Decimal("99.99"), "XX")
        self.assertEqual(result.subtotal, Decimal("33.33"))
