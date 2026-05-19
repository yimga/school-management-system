"""Shopify pillar: payment webhook view uses centralized dedupe bucket."""

from pathlib import Path

from django.test import SimpleTestCase

from apps.finance.webhook_ingress import resolve_webhook_dedup_bucket


class ViewsPaymentsDedupBucketTests(SimpleTestCase):
    def test_resolve_matches_header_priority(self):
        bucket = resolve_webhook_dedup_bucket(
            "stripe",
            {"id": "evt_body"},
            headers={"Idempotency-Key": "hdr-1"},
            idempotency_header="hdr-1",
            reference_fallback="ref-fallback",
        )
        self.assertEqual(bucket, "idempotency:hdr-1")

    def test_views_payments_wires_resolve_webhook_dedup_bucket(self):
        path = Path(__file__).resolve().parents[1] / "views_payments.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("resolve_webhook_dedup_bucket", source)
        self.assertIn("duplicate_webhook_response", source)
