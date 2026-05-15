"""Gateway parse_webhook signature integration tests (no DB required for school stub)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest

from apps.finance.gateways.flutterwave import FlutterwaveGateway
from apps.finance.gateways.mtn_momo import MTNMoMoGateway
from apps.finance.gateways.orange_money import OrangeMoneyGateway
from apps.finance.gateways.paystack import PaystackGateway
from apps.finance.gateways.stripe import StripeGateway


class _School:
    pk = 1
    slug = "test-school"


class StripeWebhookSignatureTests(unittest.TestCase):
    def test_invalid_signature_returns_failure_result(self):
        cfg = {"secret_key": "sk_live_x", "webhook_secret": "whsec_test"}
        gw = StripeGateway(_School(), cfg)
        body = b'{"type":"payment_intent.succeeded","data":{"object":{"id":"pi_x","status":"succeeded"}}}'
        # Wrong signature
        result = gw.parse_webhook(
            json.loads(body),
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
            raw_body=body,
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertIn("Stripe webhook signature failed", result.message or "")

    def test_valid_signature_parses_event(self):
        cfg = {"secret_key": "sk_live_x", "webhook_secret": "whsec_test"}
        gw = StripeGateway(_School(), cfg)
        ts = int(time.time())
        body = b'{"type":"payment_intent.succeeded","data":{"object":{"id":"pi_x","status":"succeeded"}}}'
        signed = f"{ts}.".encode() + body
        sig = hmac.new(b"whsec_test", signed, hashlib.sha256).hexdigest()
        result = gw.parse_webhook(
            json.loads(body),
            headers={"Stripe-Signature": f"t={ts},v1={sig}"},
            raw_body=body,
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(result.transaction_id, "pi_x")


class PaystackWebhookSignatureTests(unittest.TestCase):
    def test_invalid_signature_returns_failure(self):
        cfg = {"secret_key": "sk_live_paystack"}
        gw = PaystackGateway(_School(), cfg)
        body = b'{"event":"charge.success","data":{"reference":"ref_1","status":"success"}}'
        result = gw.parse_webhook(
            json.loads(body),
            headers={"x-paystack-signature": "deadbeef"},
            raw_body=body,
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertIn("Paystack webhook signature failed", result.message or "")

    def test_valid_signature_parses_event(self):
        cfg = {"secret_key": "sk_live_paystack"}
        gw = PaystackGateway(_School(), cfg)
        body = b'{"event":"charge.success","data":{"reference":"ref_1","status":"success"}}'
        sig = hmac.new(b"sk_live_paystack", body, hashlib.sha512).hexdigest()
        result = gw.parse_webhook(
            json.loads(body),
            headers={"x-paystack-signature": sig},
            raw_body=body,
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(result.transaction_id, "ref_1")


class FlutterwaveWebhookSignatureTests(unittest.TestCase):
    def test_invalid_hash_returns_failure(self):
        cfg = {"secret_key": "FLWSECK-x", "secret_hash": "hash_value"}
        gw = FlutterwaveGateway(_School(), cfg)
        body = b'{"event":"charge.completed","data":{"tx_ref":"tx_1","status":"successful"}}'
        result = gw.parse_webhook(
            json.loads(body),
            headers={"verif-hash": "wrong"},
            raw_body=body,
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.success)

    def test_valid_hash_parses_event(self):
        cfg = {"secret_key": "FLWSECK-x", "secret_hash": "hash_value"}
        gw = FlutterwaveGateway(_School(), cfg)
        body = b'{"event":"charge.completed","data":{"tx_ref":"tx_1","status":"successful"}}'
        result = gw.parse_webhook(
            json.loads(body),
            headers={"verif-hash": "hash_value"},
            raw_body=body,
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(result.transaction_id, "tx_1")


class AggregatorWebhookSignatureTests(unittest.TestCase):
    def test_mtn_momo_invalid_signature_returns_failure(self):
        cfg = {
            "subscription_key": "k",
            "api_user": "u",
            "api_key": "secret123",
            "webhook_signature": {
                "required": True,
                "secret": "secret123",
                "header_name": "X-Sig",
                "algorithm": "sha256",
            },
        }
        gw = MTNMoMoGateway(_School(), cfg)
        body = b'{"transaction_id":"tx1","status":"success"}'
        result = gw.parse_webhook(
            json.loads(body),
            headers={"X-Sig": "deadbeef"},
            raw_body=body,
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.success)

    def test_orange_money_no_signature_required_passes(self):
        # When webhook_signature is not set, current behavior allows the parse.
        cfg = {"client_id": "c", "client_secret": "s", "merchant_key": "m"}
        gw = OrangeMoneyGateway(_School(), cfg)
        body = b'{"transaction_id":"tx2","status":"successful"}'
        result = gw.parse_webhook(json.loads(body), headers={})
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(result.transaction_id, "tx2")


if __name__ == "__main__":
    unittest.main()
