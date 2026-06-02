"""Decimal JSON helpers (Shopify pillar)."""

import json
from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.json_decimal import DecimalJSONEncoder, amount_str, quantize_money


class JsonDecimalTests(SimpleTestCase):
    def test_amount_str_preserves_cent_math(self):
        self.assertEqual(amount_str(Decimal("0.1") + Decimal("0.2")), "0.30")

    def test_encoder_emits_strings_not_float(self):
        payload = json.dumps({"amount": Decimal("99.99")}, cls=DecimalJSONEncoder)
        self.assertIn('"99.99"', payload)
        self.assertNotIn("99.989999", payload)


class QuantizeMoneyTests(SimpleTestCase):
    def test_rounds_three_places_half_up(self):
        self.assertEqual(quantize_money(Decimal("10.005")), Decimal("10.01"))

    def test_pads_one_place_to_two(self):
        self.assertEqual(quantize_money("3.1"), Decimal("3.10"))

    def test_none_is_zero(self):
        self.assertEqual(quantize_money(None), Decimal("0.00"))

    def test_returns_decimal_type(self):
        self.assertIsInstance(quantize_money(5), Decimal)

    def test_preserves_exact_two_place_value(self):
        self.assertEqual(quantize_money(Decimal("123.45")), Decimal("123.45"))
