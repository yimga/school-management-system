"""§0.1.5 Wave 1: payment webhook accepts POST without CSRF (provider callbacks)."""
from django.test import Client, TestCase


class PaymentWebhookSot0155Tests(TestCase):
    def test_unknown_provider_post_without_csrf_returns_forbidden_not_csrf_failure(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post(
            "/finance/payments/webhook/nonexistent-provider-xyz/",
            data=b"{}",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)
        self.assertNotIn(b"CSRF", r.content)
