"""CEZGP 1521 — quiet_hours deferral on payment receipt intents."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.finance.payment_notification_intent import dispatch_payment_received_intent


class PaymentNotificationQuietHoursTests(SimpleTestCase):

    @patch("apps.policies.resolvers.is_within_quiet_hours", return_value=True)
    def test_dispatch_deferred_during_quiet_hours(self, _mock_qh):
        school = MagicMock(pk=1)
        payment = MagicMock(pk=99, amount=Decimal("10.00"), invoice=None, student=None)
        result = dispatch_payment_received_intent(school=school, payment=payment)
        self.assertEqual(result.get("reason"), "quiet_hours")
        self.assertTrue(result.get("deferred"))
