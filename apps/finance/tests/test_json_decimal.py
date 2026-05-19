"""Decimal JSON helpers (Shopify pillar)."""

import json
from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.json_decimal import DecimalJSONEncoder, amount_str


class JsonDecimalTests(SimpleTestCase):
    def test_amount_str_preserves_cent_math(self):
        self.assertEqual(amount_str(Decimal("0.1") + Decimal("0.2")), "0.30")

    def test_encoder_emits_strings_not_float(self):
        payload = json.dumps({"amount": Decimal("99.99")}, cls=DecimalJSONEncoder)
        self.assertIn('"99.99"', payload)
        self.assertNotIn("99.989999", payload)
