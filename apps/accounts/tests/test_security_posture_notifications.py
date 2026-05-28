
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.profile_security_evaluation import is_security_posture_review_due
from apps.accounts.security_posture_notifications import (
    POSTURE_NOTIFICATION_TITLE,
    SESSION_MODAL_ACK_KEY,
    acknowledge_session_modal,
    corner_notifications_for_request,
    ensure_quarterly_posture_notification,
    inline_security_posture_banner_active,
    security_posture_zone,
    should_show_session_modal,
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

    def test_inline_banner_deprecated_off(self):
        rf = RequestFactory()
        request = rf.get("/super/")
        request.user = self.user
        request.session = {}
        self.assertFalse(inline_security_posture_banner_active(request))

    def test_session_modal_shows_until_ack(self):
        rf = RequestFactory()
        request = rf.get("/super/")
        request.user = self.user
        request.session = {}
        zone = security_posture_zone(
            score=30,
            meets_platform_minimum=False,
            security_posture_review_due=True,
            security_posture_blocked=True,
        )
        self.assertEqual(zone, "critical")
        self.assertTrue(should_show_session_modal(request, zone=zone))
        acknowledge_session_modal(request)
        self.assertTrue(request.session.get(SESSION_MODAL_ACK_KEY))
        self.assertFalse(should_show_session_modal(request, zone=zone))

    def test_corner_payload_when_review_due(self):
        rf = RequestFactory()
        request = rf.get("/super/")
        request.user = self.user
        request.session = {}
        payloads = corner_notifications_for_request(request)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["title"], POSTURE_NOTIFICATION_TITLE)

    def test_corner_empty_when_not_due(self):
        self.user.last_security_posture_review_at = timezone.now()
        self.user.save(update_fields=["last_security_posture_review_at"])
        self.assertFalse(is_security_posture_review_due(self.user))
        rf = RequestFactory()
        request = rf.get("/")
        request.user = self.user
        request.session = {}
        self.assertEqual(corner_notifications_for_request(request), [])
