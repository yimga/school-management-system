from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.profile_security_evaluation import is_security_posture_review_due
from apps.accounts.security_posture_notifications import (
    POSTURE_NOTIFICATION_TITLE,
    corner_notifications_for_request,
    ensure_quarterly_posture_notification,
    inline_security_posture_banner_active,
)


class SecurityPostureNotificationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="posture_notify",
            email="posture@example.com",
            password="Test1234!long",
        )

    def test_ensure_creates_single_unread_notification(self):
        note = ensure_quarterly_posture_notification(self.user)
        self.assertIsNotNone(note)
        again = ensure_quarterly_posture_notification(self.user)
        self.assertEqual(note.pk, again.pk)

    def test_inline_banner_active_when_due(self):
        rf = RequestFactory()
        request = rf.get("/super/")
        request.user = self.user
        request.session = {}
        self.assertTrue(inline_security_posture_banner_active(request))

    def test_corner_empty_when_inline_banner_active(self):
        rf = RequestFactory()
        request = rf.get("/super/")
        request.user = self.user
        request.session = {}
        self.assertEqual(corner_notifications_for_request(request), [])

    def test_corner_empty_when_not_due(self):
        self.user.last_security_posture_review_at = timezone.now()
        self.user.save(update_fields=["last_security_posture_review_at"])
        self.assertFalse(is_security_posture_review_due(self.user))
        rf = RequestFactory()
        request = rf.get("/")
        request.user = self.user
        request.session = {}
        self.assertEqual(corner_notifications_for_request(request), [])
