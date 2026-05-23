"""SODP: transactional email dedupe via EmailDeliveryEvent.idempotency_key."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.schoolops.email_delivery import send_transactional
from apps.schoolops.models_email_delivery import EmailDeliveryEvent


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP=0,
)
class EmailDeliveryIdempotencyTests(TestCase):
    databases = {"default"}

    @patch("apps.schoolops.email_delivery.get_resolved_smtp_config")
    def test_duplicate_idempotency_key_skips_second_smtp(self, mock_cfg):
        mock_cfg.return_value = {
            "host": "localhost",
            "port": 25,
            "host_user": "",
            "host_password": "",
            "use_tls": False,
            "default_from_email": "noreply@runmycampus.com",
            "connection_timeout_seconds": 5,
        }
        idem = "sodp-test-idem-1"
        first = send_transactional(
            subject="Test",
            body="Body",
            to="user@example.com",
            idempotency_key=idem,
        )
        self.assertTrue(first.get("ok"))
        self.assertEqual(
            EmailDeliveryEvent.objects.filter(idempotency_key=idem).count(),
            1,
        )

        second = send_transactional(
            subject="Test again",
            body="Body",
            to="user@example.com",
            idempotency_key=idem,
        )
        self.assertTrue(second.get("deduplicated"))
        self.assertEqual(
            EmailDeliveryEvent.objects.filter(idempotency_key=idem).count(),
            1,
        )
        self.assertEqual(second.get("delivery_event_id"), first.get("delivery_event_id"))
