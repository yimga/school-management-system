"""Shopify pillar: payment app webhook ingress boundary."""

from django.test import SimpleTestCase

from apps.finance.webhooks.idempotency import compute_idempotency_bucket
from payment.webhook_ingress import (
    compute_idempotency_bucket as payment_compute,
    find_processed_duplicate,
)


class PaymentWebhookIngressTests(SimpleTestCase):
    def test_idempotency_reexport_matches_finance(self):
        payload = {"id": "evt_123"}
        self.assertEqual(
            payment_compute("stripe", payload, {}),
            compute_idempotency_bucket("stripe", payload, {}),
        )

    def test_find_processed_duplicate_importable(self):
        self.assertTrue(callable(find_processed_duplicate))
