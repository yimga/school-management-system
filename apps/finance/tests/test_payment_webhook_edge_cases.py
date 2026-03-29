"""Payment webhook edge cases beyond provider contract tests (batch 14 #133)."""

import hashlib
import hmac

from django.test import TestCase
from django.urls import reverse

from apps.finance.models import WebhookLog
from apps.siteconfig.models import Integration


class PaymentWebhookEdgeCaseTests(TestCase):
    def test_get_method_returns_405(self):
        url = reverse(
            "finance:payment_webhook", kwargs={"provider_slug": "any-provider"}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_unknown_provider_returns_403_without_webhook_log(self):
        before = WebhookLog.objects.count()
        url = reverse(
            "finance:payment_webhook",
            kwargs={"provider_slug": "unknown-provider-xyz-batch14"},
        )
        response = self.client.post(
            url,
            data=b"{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(WebhookLog.objects.count(), before)

    def test_non_utf8_body_creates_invalid_webhook_log_after_signature_ok(self):
        secret = "edge-secret-utf8"
        slug = "edge-utf8-payments"
        Integration.objects.create(
            name="Edge UTF-8",
            slug=slug,
            provider="payments",
            enabled=True,
            config={"webhook_secret": secret},
        )
        raw = b"\xff\xfe"
        signature = hmac.new(secret.encode("ascii"), raw, hashlib.sha256).hexdigest()
        url = reverse("finance:payment_webhook", kwargs={"provider_slug": slug})
        response = self.client.post(
            url,
            data=raw,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 400)
        log = WebhookLog.objects.latest("pk")
        self.assertEqual(log.status, WebhookLog.Status.INVALID)
        self.assertEqual(log.response_status, 400)
        self.assertIn("Invalid JSON", log.error_message or "")
