"""SFDP 1430 — unified webhook normalizer."""

from __future__ import annotations

import unittest
from decimal import Decimal

from apps.finance.webhooks.normalizer import (
    is_explicit_non_success,
    normalize_provider_payload,
)


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

    def test_mpesa_daraja_stk_success(self):
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "29115-34620561-1",
                    "CheckoutRequestID": "ws_CO_191220191020363925",
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 1.0},
                            {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
                            {"Name": "TransactionDate", "Value": 20191219102115},
                            {"Name": "PhoneNumber", "Value": 254708374149},
                            {"Name": "BillRefNumber", "Value": "88"},
                        ]
                    },
                }
            }
        }
        event = normalize_provider_payload("mpesa_daraja", payload)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_id, "ws_CO_191220191020363925")
        self.assertEqual(event.invoice_id, 88)
        self.assertEqual(event.currency, "KES")
        self.assertEqual(event.amount_decimal, Decimal("1"))
        self.assertTrue(event.is_success())

        # Alias slug used by some webhook routes.
        alias = normalize_provider_payload("mpesa", payload)
        self.assertIsNotNone(alias)
        assert alias is not None
        self.assertEqual(alias.event_id, event.event_id)

    def test_mpesa_daraja_stk_failure(self):
        payload = {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": "ws_CO_FAIL_1",
                    "ResultCode": 1032,
                    "ResultDesc": "Request cancelled by user",
                }
            }
        }
        event = normalize_provider_payload("mpesa_daraja", payload)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_id, "ws_CO_FAIL_1")
        self.assertFalse(event.is_success())


class WebhookSuccessGateTests(unittest.TestCase):
    """SFDP: a signed FAILED webhook must never post a Payment.

    ``is_explicit_non_success`` is the exact predicate the webhook view gates on
    before ``record_provider_payment`` (which feeds the fractional ledger and
    grants enrollment clearance). These are MUST-FIRE tests: if the predicate
    regressed to always-False, a declined callback with a valid amount would
    clear a non-paying student.
    """

    def _flutterwave(self, status):
        return normalize_provider_payload(
            "flutterwave",
            {
                "event": "charge.completed",
                "data": {
                    "tx_ref": "FLW-GATE",
                    "status": status,
                    "amount": 15000,
                    "currency": "XAF",
                    "meta": {"invoice_id": 5},
                },
            },
        )

    def test_gate_blocks_explicit_failure_statuses(self):
        # Major-unit rails (MoMo/Flutterwave/Orange) carry a real amount even on
        # failure, so these are the exposed cases the gate must catch.
        for status in ("failed", "declined", "cancelled", "reversed", "pending"):
            with self.subTest(status=status):
                event = self._flutterwave(status)
                self.assertIsNotNone(event)
                self.assertFalse(event.is_success())
                self.assertTrue(
                    is_explicit_non_success(event),
                    f"status {status!r} must block payment posting",
                )

    def test_gate_allows_success(self):
        event = self._flutterwave("successful")
        self.assertTrue(event.is_success())
        self.assertFalse(is_explicit_non_success(event))

    def test_gate_allows_empty_status_no_regression(self):
        # A provider that omits status must NOT be blocked (prior behaviour).
        event = normalize_provider_payload(
            "mtn_momo",
            {"referenceId": "MTN-NOSTATUS", "amount": "1000", "currency": "XAF"},
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.status, "")
        self.assertFalse(is_explicit_non_success(event))

    def test_gate_allows_none_event(self):
        self.assertFalse(is_explicit_non_success(None))

    def test_gate_blocks_mpesa_stk_failure(self):
        event = normalize_provider_payload(
            "mpesa_daraja",
            {"Body": {"stkCallback": {"CheckoutRequestID": "ws_CO_X", "ResultCode": 1032}}},
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.status, "failed")
        self.assertTrue(is_explicit_non_success(event))
