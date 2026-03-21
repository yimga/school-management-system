"""§0.1.5 Wave 2: SMS optional; email fallback when no provider."""
from unittest.mock import patch

from django.test import TestCase

from apps.communication.notification_service import send_sms


class SmsFallbackSot0155Tests(TestCase):
    @patch("apps.communication.notification_service.get_sms_provider")
    @patch("apps.communication.notification_service.send_email")
    def test_no_sms_provider_uses_fallback_email(self, mock_email, mock_provider):
        mock_provider.return_value = None
        mock_email.return_value = True
        ok = send_sms(
            "+15551234567",
            "hello",
            fallback_email="parent@example.com",
        )
        self.assertTrue(ok)
        mock_email.assert_called_once()
