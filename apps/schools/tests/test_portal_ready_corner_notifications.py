"""Portal-ready corner toast on first authenticated visit."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.context_processors_security import account_security_context
from apps.finance.models import Notification
from apps.schools.portal_ready_corner_notifications import (
    mark_portal_ready_corner_dismissed,
    portal_ready_corner_for_request,
)
from apps.schools.signup_portal_channel_notifications import PORTAL_READY_INBOX_TITLE


@override_settings(
    WEB_PUSH_VAPID_PUBLIC_KEY="test-public",
    WEB_PUSH_VAPID_PRIVATE_KEY="test-private",
)
class PortalReadyCornerNotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="corner@test",
            email="corner@test",
            password="Pass1234!",
            role=User.Role.ADMIN,
        )
        self.note = Notification.objects.create(
            recipient=self.user,
            title=PORTAL_READY_INBOX_TITLE,
            message="Your school Demo is live.",
            link="https://runmycampus.com/authentication/login/",
            is_read=False,
        )
        self.factory = RequestFactory()

    def _request(self):
        request = self.factory.get("/authentication/backend/")
        request.user = self.user
        request.session = self.client.session
        return request

    def test_unread_portal_ready_surfaces_corner_payload(self):
        payloads = portal_ready_corner_for_request(self._request())
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["id"], str(self.note.pk))
        self.assertTrue(payloads[0]["browser_notify"])

    def test_dismissed_session_hides_corner(self):
        request = self._request()
        mark_portal_ready_corner_dismissed(request, str(self.note.pk))
        self.assertEqual(portal_ready_corner_for_request(request), [])

    def test_context_processor_includes_portal_ready_corner(self):
        request = self._request()
        ctx = account_security_context(request)
        corners = ctx.get("rmc_corner_notifications") or []
        self.assertTrue(any(c.get("source") == "portal_ready" for c in corners))

    def test_mark_read_clears_unread_inbox_row(self):
        self.note.is_read = True
        self.note.save(update_fields=["is_read"])
        self.assertEqual(portal_ready_corner_for_request(self._request()), [])
