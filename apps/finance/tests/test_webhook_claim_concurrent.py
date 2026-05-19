"""Webhook claim race-safety — DB unique constraint + duplicate path (Shopify pillar)."""

from django.test import TestCase

from apps.finance.models import WebhookLog
from apps.finance.webhooks.claim import claim_webhook_processing


class WebhookClaimRaceSafetyTests(TestCase):
    def test_rapid_sequential_claims_single_row(self):
        bucket = "stripe:evt_rapid_seq_1"
        outcomes = []
        for _ in range(4):
            outcome, _log = claim_webhook_processing(
                provider="stripe",
                bucket=bucket,
                reference_id=bucket,
                client_ip="127.0.0.1",
            )
            outcomes.append(outcome)

        self.assertEqual(outcomes, ["claimed", "duplicate", "duplicate", "duplicate"])
        self.assertEqual(
            WebhookLog.objects.filter(
                provider="stripe", idempotency_bucket=bucket
            ).count(),
            1,
        )

    def test_provider_bucket_unique_constraint_registered(self):
        names = {
            c.name
            for c in WebhookLog._meta.constraints
            if hasattr(c, "name")
        }
        self.assertIn("finance_webhooklog_uniq_provider_bucket", names)
