"""Atomic webhook idempotency claim (Shopify pillar)."""

from django.test import TestCase

from apps.finance.models import WebhookLog
from apps.finance.webhooks.claim import claim_webhook_processing


class WebhookClaimTests(TestCase):
    def test_second_claim_is_duplicate(self):
        bucket = "stripe:evt_claim_test_1"
        r1, log1 = claim_webhook_processing(
            provider="stripe",
            bucket=bucket,
            reference_id="evt_claim_test_1",
            client_ip="127.0.0.1",
        )
        self.assertEqual(r1, "claimed")
        self.assertIsNotNone(log1)

        r2, log2 = claim_webhook_processing(
            provider="stripe",
            bucket=bucket,
            reference_id="evt_claim_test_1",
            client_ip="127.0.0.1",
        )
        self.assertEqual(r2, "duplicate")
        self.assertEqual(log1.pk, log2.pk)
        self.assertEqual(
            WebhookLog.objects.filter(
                provider="stripe", idempotency_bucket=bucket
            ).count(),
            1,
        )
