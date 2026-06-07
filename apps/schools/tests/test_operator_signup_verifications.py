"""Operator signup-verification console: list + resend + regenerate (2026-06-06).

Tested at the view layer via RequestFactory so the assertions target THIS view's
logic, not the manager-host / MFA control-plane middleware (exercised elsewhere).
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.schools.models import School, SignupVerification
from apps.schools.super_views_signup_verifications import (
    SignupVerificationActionView,
    SignupVerificationConsoleView,
)


class OperatorSignupVerificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.op = User.objects.create_user(
            username="op-sv@rmc.test", email="op-sv@rmc.test", password="pw-12345",
            is_staff=True, is_superuser=True,
        )
        self.school = School.objects.create(
            name="Cedar School", slug="cedar-sv", subdomain="cedar-sv",
            is_active=False, country_code="US", settings={},
        )
        self.verif = SignupVerification.objects.create(
            school=self.school, email="owner@cedar.test",
            expires_at=timezone.now() - timedelta(days=1),  # expired
        )
        self.rf = RequestFactory()

    def _req(self, method, data=None):
        req = getattr(self.rf, method)("/super/signup-verifications/", data or {})
        req.user = self.op
        req.session = SessionStore()
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def test_console_lists_pending_signup(self):
        with mock.patch(
            "apps.schools.super_views_signup_verifications.render"
        ) as rnd:
            rnd.side_effect = lambda r, t, c: HttpResponse("ok")
            resp = SignupVerificationConsoleView.as_view()(self._req("get"))
            ctx = rnd.call_args.args[2]
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(row["email"] == "owner@cedar.test" for row in ctx["rows"]))
        self.assertEqual(ctx["counts"]["total"], 1)
        self.assertEqual(ctx["counts"]["expired"], 1)

    def test_resend_extends_expiry_keeps_token(self):
        old_token = self.verif.token
        with mock.patch(
            "apps.schools.super_views_signup_verifications._send_signup_verification_email"
        ) as send:
            resp = SignupVerificationActionView.as_view()(
                self._req("post", {"action": "resend"}), pk=self.verif.pk
            )
        self.assertEqual(resp.status_code, 302)
        self.verif.refresh_from_db()
        self.assertEqual(self.verif.token, old_token)
        self.assertGreater(self.verif.expires_at, timezone.now())
        send.assert_called_once()

    def test_regenerate_rotates_token_and_extends(self):
        old_token = self.verif.token
        with mock.patch(
            "apps.schools.super_views_signup_verifications._send_signup_verification_email"
        ) as send:
            resp = SignupVerificationActionView.as_view()(
                self._req("post", {"action": "regenerate"}), pk=self.verif.pk
            )
        self.assertEqual(resp.status_code, 302)
        self.verif.refresh_from_db()
        self.assertNotEqual(self.verif.token, old_token)
        self.assertGreater(self.verif.expires_at, timezone.now())
        send.assert_called_once()

    def test_verified_signup_is_not_resent(self):
        self.verif.verified_at = timezone.now()
        self.verif.save(update_fields=["verified_at"])
        with mock.patch(
            "apps.schools.super_views_signup_verifications._send_signup_verification_email"
        ) as send:
            resp = SignupVerificationActionView.as_view()(
                self._req("post", {"action": "resend"}), pk=self.verif.pk
            )
        self.assertEqual(resp.status_code, 302)
        send.assert_not_called()
