from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.accounts.context_processors_security import account_security_context
from apps.accounts.security_posture_notifications import (
    SESSION_CORNER_SNOOZE_KEY,
    snooze_corner_notifications,
)


class AccountSecurityContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ctx_security",
            email="ctx@example.com",
            password="Test1234!long",
        )
        self.rf = RequestFactory()

    def test_anonymous_returns_empty(self):
        request = self.rf.get("/super/")
        request.user = AnonymousUser()
        request.session = {}
        self.assertEqual(account_security_context(request), {})

    def test_authenticated_exposes_inline_and_corner_fields(self):
        request = self.rf.get("/super/")
        request.user = self.user
        request.session = {}
        ctx = account_security_context(request)
        self.assertTrue(ctx["security_posture_review_due"])
        self.assertTrue(ctx["security_posture_inline_banner"])
        self.assertFalse(ctx["security_posture_corner_snoozed"])
        self.assertEqual(ctx["rmc_corner_notifications"], [])

    def test_snooze_hides_inline_and_corner(self):
        request = self.rf.get("/super/")
        request.user = self.user
        request.session = {}
        snooze_corner_notifications(request)
        self.assertTrue(request.session.get(SESSION_CORNER_SNOOZE_KEY))
        ctx = account_security_context(request)
        self.assertFalse(ctx["security_posture_inline_banner"])
        self.assertTrue(ctx["security_posture_corner_snoozed"])
        self.assertEqual(ctx["rmc_corner_notifications"], [])
