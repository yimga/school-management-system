"""NOTIF-001 — tenant lifecycle notification facade."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.platform_runtime.tenant_lifecycle_notifications import (
    DELIVERY_DUPLICATE,
    DELIVERY_QUEUED,
    EVENT_PROVISIONING_COMPLETED,
    EVENT_PROVISIONING_FAILED,
    emit_tenant_lifecycle_notification,
    lifecycle_notification_history,
    should_suppress_duplicate,
)
from apps.schools.models import School


class TenantLifecycleNotificationFacadeTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Notify Facade School",
            slug="notify-facade",
            subdomain="notify-facade",
            is_active=True,
        )

    @patch(
        "apps.schools.signup_completion_notifications.notify_provisioning_failed_operator"
    )
    def test_provisioning_failed_dispatched_once(self, mock_failed):
        first = emit_tenant_lifecycle_notification(
            self.school,
            EVENT_PROVISIONING_FAILED,
            contact_email="owner@notify.test",
            error="schema timeout",
        )
        second = emit_tenant_lifecycle_notification(
            self.school,
            EVENT_PROVISIONING_FAILED,
            contact_email="owner@notify.test",
            error="schema timeout",
        )
        self.assertEqual(first["status"], DELIVERY_QUEUED)
        self.assertEqual(second["status"], DELIVERY_DUPLICATE)
        mock_failed.assert_called_once()

    @patch(
        "apps.schools.signup_completion_notifications.notify_provisioning_failed_operator"
    )
    def test_different_error_fingerprint_allows_new_alert(self, mock_failed):
        emit_tenant_lifecycle_notification(
            self.school,
            EVENT_PROVISIONING_FAILED,
            contact_email="owner@notify.test",
            error="error A",
        )
        emit_tenant_lifecycle_notification(
            self.school,
            EVENT_PROVISIONING_FAILED,
            contact_email="owner@notify.test",
            error="error B",
        )
        self.assertEqual(mock_failed.call_count, 2)
        self.assertFalse(
            should_suppress_duplicate(
                self.school, EVENT_PROVISIONING_FAILED, error="error C"
            )
        )

    @patch("apps.schools.signup_completion_notifications.notify_tenant_signup_completed")
    def test_history_records_dispatches(self, mock_completed):
        mock_completed.return_value = True
        emit_tenant_lifecycle_notification(
            self.school,
            EVENT_PROVISIONING_COMPLETED,
            contact_email="owner@notify.test",
        )
        history = lifecycle_notification_history(self.school)
        events = [row["event"] for row in history]
        self.assertIn(EVENT_PROVISIONING_COMPLETED, events)
