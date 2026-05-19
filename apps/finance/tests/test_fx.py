"""FX Decimal helpers (G-19)."""

from decimal import Decimal
from unittest import TestCase

from apps.finance.fx import convert_amount_decimal, exchange_rate_decimal


class FxDecimalTests(TestCase):
    def test_usd_to_ngn_rate(self):
        rate = exchange_rate_decimal("USD", "NGN")
        self.assertIsNotNone(rate)
        self.assertGreater(rate, Decimal("0"))

    def test_convert_amount_decimal(self):
        out = convert_amount_decimal(Decimal("100"), "USD", "NGN")
        self.assertGreater(out, Decimal("0"))
