"""Quarterly posture notification must be idempotent + self-healing.

Regression for the "Quarterly security review due" toast storm: the
non-atomic check-then-create produced dozens of duplicate unread rows under
the new-tenant request herd, each with a different pk, defeating the corner
toast's id de-dup.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.security_posture_notifications import (
    build_corner_notification_payload,
    corner_notifications_for_request,
    ensure_quarterly_posture_notification,
    POSTURE_NOTIFICATION_TITLE,
)
from apps.finance.models import Notification


class PostureNotificationIdempotencyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="posture_user",
            email="posture@example.com",
            password="Test1234!long",
        )

    def _unread_count(self):
        return Notification.objects.filter(
            recipient=self.user,
            title=POSTURE_NOTIFICATION_TITLE,
            is_read=False,
        ).count()

    def test_creates_exactly_one_when_none(self):
        note = ensure_quarterly_posture_notification(self.user)
        self.assertIsNotNone(note)
        self.assertEqual(self._unread_count(), 1)

    def test_idempotent_repeat_calls_do_not_multiply(self):
        first = ensure_quarterly_posture_notification(self.user)
        for _ in range(10):
            again = ensure_quarterly_posture_notification(self.user)
            self.assertEqual(again.pk, first.pk)
        self.assertEqual(self._unread_count(), 1)

    def test_collapses_existing_duplicate_storm(self):
        # Legacy storms are collapsed on read; unread duplicates are blocked at DB layer now.
        keeper = Notification.objects.create(
            recipient=self.user,
            title=POSTURE_NOTIFICATION_TITLE,
            message="keeper",
            severity=Notification.Severity.WARNING,
            is_read=False,
        )
        for _ in range(24):
            Notification.objects.create(
                recipient=self.user,
                title=POSTURE_NOTIFICATION_TITLE,
                message="historical read copy",
                severity=Notification.Severity.WARNING,
                is_read=True,
            )
        note = ensure_quarterly_posture_notification(self.user)
        self.assertEqual(note.pk, keeper.pk)
        self.assertEqual(self._unread_count(), 1)

    def test_payload_carries_stable_dedup_key(self):
        note = ensure_quarterly_posture_notification(self.user)
        payload = build_corner_notification_payload(note, review_url="/x/")
        self.assertEqual(payload["dedup_key"], "security-posture-review")

    def test_context_path_returns_single_payload_after_storm(self):
        Notification.objects.create(
            recipient=self.user,
            title=POSTURE_NOTIFICATION_TITLE,
            message="keeper",
            severity=Notification.Severity.WARNING,
            is_read=False,
        )
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {}
        payloads = corner_notifications_for_request(request)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(self._unread_count(), 1)
