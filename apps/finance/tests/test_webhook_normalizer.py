"""SFDP 1430 — unified webhook normalizer."""

from __future__ import annotations

import unittest
from decimal import Decimal

from apps.finance.webhooks.normalizer import normalize_provider_payload


class WebhookNormalizerTests(unittest.TestCase):
    def test_paystack_charge_success(self):
        payload = {
            "event": "charge.success",
            "data": {
                "reference": "PSK-123",
                "status": "success",
                "amount": 500000,
                "currency": "NGN",
                "metadata": {"invoice_id": 42, "school_id": 7},
            },
        }
        event = normalize_provider_payload("paystack", payload)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_id, "PSK-123")
        self.assertEqual(event.invoice_id, 42)
        self.assertEqual(event.school_id, 7)
        self.assertTrue(event.is_success())
        self.assertEqual(event.amount_decimal, Decimal("5000"))

    def test_stripe_payment_intent_succeeded(self):
        payload = {
            "id": "evt_stripe_1",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_abc",
                    "status": "succeeded",
                    "amount_received": 25000,
                    "currency": "usd",
                    "metadata": {"invoice_id": "99", "school_id": "3"},
                }
            },
        }
        event = normalize_provider_payload("stripe", payload)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_id, "pi_abc")
        self.assertEqual(event.invoice_id, 99)
        self.assertEqual(event.school_id, 3)
        self.assertEqual(event.amount_decimal, Decimal("250"))
        self.assertTrue(event.is_success())

    def test_flutterwave_success(self):
        payload = {
            "event": "charge.completed",
            "data": {
                "tx_ref": "FLW-9",
                "status": "successful",
                "amount": 15000,
                "currency": "XAF",
            },
        }
        event = normalize_provider_payload("flutterwave", payload)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.provider, "flutterwave")
        self.assertTrue(event.is_success())

    def test_flutterwave_missing_currency_uses_platform_default(self):
        from django.test import override_settings

        payload = {
            "event": "charge.completed",
            "data": {
                "tx_ref": "FLW-NO-CCY",
                "status": "successful",
                "amount": 15000,
            },
        }
        with override_settings(PLATFORM_DEFAULT_CURRENCY="USD"):
            event = normalize_provider_payload("flutterwave", payload)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.currency, "USD")
