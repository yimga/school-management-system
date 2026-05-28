"""SFDP 1431 — payment.received notification intents."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.schoolops.notification_intent import render_notification_intent
from apps.schoolops.sms_templates import render_payment_received_sms


class PaymentNotificationIntentTests(TestCase):
    def test_render_payment_received_email(self):
        subject, body, html = render_notification_intent(
            template_key="payment_received",
            locale="en",
            context={
                "student_name": "Ada",
                "amount": "100.00",
                "currency": "NGN",
                "reference": "INV-1",
            },
        )
        self.assertIn("Payment received", subject)
        self.assertIn("Ada", body)
        self.assertIsNone(html)

    def test_render_payment_received_sms_under_160(self):
        body = render_payment_received_sms(
            locale="en",
            context={"student_name": "Ada", "reference": "INV-1"},
        )
        self.assertLessEqual(len(body), 160)
        self.assertIn("Ada", body)

    @patch("apps.schoolops.email_delivery.send_transactional")
    def test_dispatch_skips_without_school(self, mock_send):
        from apps.finance.payment_notification_intent import dispatch_payment_received_intent

        result = dispatch_payment_received_intent(school=None, payment=None)
        self.assertEqual(result["dispatched"], 0)
        mock_send.assert_not_called()
