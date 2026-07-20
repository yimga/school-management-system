"""Tests for apps.finance.webhooks.signature_verifiers — pure stdlib, no DB."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest

from apps.finance.webhooks.signature_verifiers import (
    verify_aggregator_hmac,
    verify_flutterwave,
    verify_mpesa_daraja,
    verify_mpesa_stk_callback_shape,
    verify_paystack,
    verify_stripe,
)


class StripeVerifierTests(unittest.TestCase):
    secret = "whsec_unit_test_only"

    def _signed(self, body: bytes, ts: int) -> dict:
        signed = f"{ts}.".encode() + body
        digest = hmac.new(self.secret.encode(), signed, hashlib.sha256).hexdigest()
        return {"Stripe-Signature": f"t={ts},v1={digest}"}

    def test_valid_signature_passes(self):
        ts = int(time.time())
        body = json.dumps({"id": "evt_1"}).encode()
        ok, reason = verify_stripe(self._signed(body, ts), body, self.secret)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "")

    def test_missing_secret_fails(self):
        ok, reason = verify_stripe({}, b"{}", "")
        self.assertFalse(ok)
        self.assertEqual(reason, "stripe_secret_missing")

    def test_missing_header_fails(self):
        ok, reason = verify_stripe({}, b"{}", self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "stripe_signature_header_missing")

    def test_skewed_timestamp_rejected(self):
        ts = int(time.time()) - 600  # 10 min in the past
        body = b"{}"
        ok, reason = verify_stripe(self._signed(body, ts), body, self.secret, tolerance_seconds=300)
        self.assertFalse(ok)
        self.assertEqual(reason, "stripe_timestamp_outside_tolerance")

    def test_tampered_body_rejected(self):
        ts = int(time.time())
        body = b'{"id":"evt_1"}'
        headers = self._signed(body, ts)
        ok, reason = verify_stripe(headers, b'{"id":"evt_2"}', self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "stripe_signature_mismatch")


class PaystackVerifierTests(unittest.TestCase):
    secret = "sk_test_paystack_unit"

    def test_valid_signature_passes(self):
        body = b'{"event":"charge.success"}'
        sig = hmac.new(self.secret.encode(), body, hashlib.sha512).hexdigest()
        ok, reason = verify_paystack({"x-paystack-signature": sig}, body, self.secret)
        self.assertTrue(ok, reason)

    def test_invalid_signature_fails(self):
        body = b'{}'
        ok, reason = verify_paystack({"x-paystack-signature": "deadbeef"}, body, self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "paystack_signature_mismatch")

    def test_missing_header_fails(self):
        ok, reason = verify_paystack({}, b"{}", self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "paystack_signature_header_missing")


class FlutterwaveVerifierTests(unittest.TestCase):
    def test_matching_hash_passes(self):
        ok, reason = verify_flutterwave({"verif-hash": "FLW_HASH_VALUE"}, b"", "FLW_HASH_VALUE")
        self.assertTrue(ok, reason)

    def test_missing_hash_fails(self):
        ok, reason = verify_flutterwave({"verif-hash": "wrong"}, b"", "FLW_HASH_VALUE")
        self.assertFalse(ok)
        self.assertEqual(reason, "flutterwave_verif_hash_mismatch")

    def test_missing_secret_fails(self):
        ok, reason = verify_flutterwave({"verif-hash": "x"}, b"", "")
        self.assertFalse(ok)
        self.assertEqual(reason, "flutterwave_secret_hash_missing")


class AggregatorHmacTests(unittest.TestCase):
    secret = "agg_secret"

    def test_body_only_signing_passes(self):
        body = b'{"transaction_id":"abc"}'
        digest = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        ok, reason = verify_aggregator_hmac(
            {"X-Sig": digest}, body, self.secret,
            header_name="X-Sig", algorithm="sha256",
        )
        self.assertTrue(ok, reason)

    def test_timestamp_body_signing_passes(self):
        body = b'{"id":"x"}'
        ts = int(time.time())
        signed = f"{ts}.".encode() + body
        digest = hmac.new(self.secret.encode(), signed, hashlib.sha256).hexdigest()
        ok, reason = verify_aggregator_hmac(
            {"X-Sig": digest, "X-Timestamp": str(ts)}, body, self.secret,
            header_name="X-Sig", algorithm="sha256",
            timestamp_header="X-Timestamp",
            body_template="{timestamp}.{body}",
        )
        self.assertTrue(ok, reason)

    def test_unsupported_algorithm_fails(self):
        ok, reason = verify_aggregator_hmac(
            {"X-Sig": "abc"}, b"{}", self.secret,
            header_name="X-Sig", algorithm="md4",
        )
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("aggregator_unsupported_algorithm"))


class MpesaDarajaVerifierTests(unittest.TestCase):
    secret = "mpesa_whsec_unit"

    def test_valid_hmac_passes(self):
        body = b'{"Body":{"stkCallback":{"CheckoutRequestID":"ws_1","ResultCode":0}}}'
        digest = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        ok, reason = verify_mpesa_daraja({"X-Signature": digest}, body, self.secret)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "")

    def test_missing_secret_fails(self):
        ok, reason = verify_mpesa_daraja({"X-Signature": "x"}, b"{}", "")
        self.assertFalse(ok)
        self.assertEqual(reason, "mpesa_secret_missing")

    def test_empty_body_fails(self):
        ok, reason = verify_mpesa_daraja({"X-Signature": "x"}, b"  ", self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "mpesa_body_empty")

    def test_tampered_body_fails(self):
        body = b'{"Body":{"stkCallback":{"CheckoutRequestID":"ws_1","ResultCode":0}}}'
        digest = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        ok, reason = verify_mpesa_daraja(
            {"X-Signature": digest}, b'{"Body":{"stkCallback":{"CheckoutRequestID":"ws_2","ResultCode":0}}}', self.secret
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "mpesa_signature_mismatch")

    def test_stk_shape_requires_checkout_and_result(self):
        ok, reason = verify_mpesa_stk_callback_shape({})
        self.assertFalse(ok)
        self.assertEqual(reason, "mpesa_payload_empty")
        ok, reason = verify_mpesa_stk_callback_shape(
            {"Body": {"stkCallback": {"CheckoutRequestID": "ws_1", "ResultCode": 0}}}
        )
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
