"""Shopify pillar: finance webhook ingress helpers."""

from django.test import SimpleTestCase

from apps.finance.webhook_ingress import resolve_webhook_dedup_bucket


class FinanceWebhookIngressTests(SimpleTestCase):
    def test_header_wins_over_payload_event_id(self):
        bucket = resolve_webhook_dedup_bucket(
            "stripe",
            {"id": "evt_payload"},
            headers={"Idempotency-Key": "client-key-1"},
            idempotency_header="client-key-1",
        )
        self.assertEqual(bucket, "idempotency:client-key-1")

    def test_payload_event_id_when_no_header(self):
        bucket = resolve_webhook_dedup_bucket(
            "stripe",
            {"id": "evt_abc"},
            headers={},
        )
        self.assertEqual(bucket, "stripe:evt_abc")
