"""Crafted-payload hardening for the PSP webhook normalizer.

The public payment webhook runs ``normalize_provider_payload`` on an anonymous,
attacker-controlled body BEFORE IP-whitelist, rate-limit, and signature checks.
The stripe/razorpay branches chained ``.get()`` on a value whose type the caller
controls, so a body like ``{"data": "x"}`` (stripe) or ``{"payload": "x"}``
(razorpay) raised ``AttributeError`` — an unauthenticated, pre-signature 500 (and
un-throttled, since it runs before the rate-limit gate).

Each test below would raise ``AttributeError`` against the pre-fix code, so they
FIRE on the regression rather than merely passing.
"""

from __future__ import annotations

import unittest

from apps.finance.webhooks.normalizer import normalize_provider_payload


class StripeMalformedPayloadTests(unittest.TestCase):
    def test_data_is_a_string_does_not_crash(self):
        # {"data": "x"} → payload["data"].get("object") used to raise AttributeError.
        # It now degrades safely; an unparseable event may normalize to None — the
        # point is that no exception escapes to become an unauthenticated 500.
        normalize_provider_payload("stripe", {"data": "x"})

    def test_data_object_is_a_list_does_not_crash(self):
        normalize_provider_payload("stripe", {"data": ["not", "a", "dict"]})

    def test_object_is_a_string_does_not_crash(self):
        normalize_provider_payload("stripe", {"object": "event", "data": {"object": {}}})

    def test_real_stripe_event_still_parses(self):
        payload = {
            "object": "event",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_123",
                    "status": "succeeded",
                    "amount_received": 500000,
                    "currency": "usd",
                }
            },
        }
        # Must not raise; behaviour for the well-formed event is unchanged.
        normalize_provider_payload("stripe", payload)


class RazorpayMalformedPayloadTests(unittest.TestCase):
    def test_payload_is_a_string_does_not_crash(self):
        normalize_provider_payload("razorpay", {"payload": "x"})

    def test_payment_is_a_string_does_not_crash(self):
        normalize_provider_payload("razorpay", {"payload": {"payment": "x"}})

    def test_entity_is_a_string_falls_back_to_payload(self):
        normalize_provider_payload(
            "razorpay", {"payload": {"payment": {"entity": "x"}}, "event": "captured"}
        )

    def test_real_razorpay_event_still_parses(self):
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_123",
                        "status": "captured",
                        "amount": 500000,
                        "currency": "INR",
                    }
                }
            },
        }
        normalize_provider_payload("razorpay", payload)


if __name__ == "__main__":
    unittest.main()
