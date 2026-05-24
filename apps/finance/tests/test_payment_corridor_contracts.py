"""Corridor metadata contracts (SFDP 1438–1440)."""

from django.test import SimpleTestCase

from apps.finance.payment_corridor_contracts import (
    FLUTTERWAVE_REQUIRED_METADATA_KEYS,
    PAYSTACK_REQUIRED_METADATA_KEYS,
    STRIPE_TUITION_METADATA_KEYS,
    metadata_keys_complete,
)


class PaymentCorridorContractsTests(SimpleTestCase):
    def test_paystack_metadata_complete(self):
        self.assertTrue(
            metadata_keys_complete(
                "paystack",
                {"invoice_id": 1, "school_id": 2, "extra": "ok"},
            )
        )
        self.assertFalse(metadata_keys_complete("paystack", {"invoice_id": 1}))

    def test_flutterwave_metadata_complete(self):
        self.assertEqual(
            PAYSTACK_REQUIRED_METADATA_KEYS,
            FLUTTERWAVE_REQUIRED_METADATA_KEYS,
        )
        self.assertTrue(metadata_keys_complete("flutterwave", dict.fromkeys(FLUTTERWAVE_REQUIRED_METADATA_KEYS, 1)))

    def test_stripe_tuition_metadata(self):
        self.assertIn("invoice_id", STRIPE_TUITION_METADATA_KEYS)
        self.assertTrue(metadata_keys_complete("stripe", {"invoice_id": 9, "school_id": 3}))
