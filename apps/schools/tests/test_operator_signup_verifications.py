"""Operator signup-verification console: list + resend + regenerate (2026-06-06)."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School, SignupVerification

HOST = "manager.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"])
class OperatorSignupVerificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.op = User.objects.create_user(
            username="op-sv@rmc.test", email="op-sv@rmc.test", password="pw-12345",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.op)
        session = self.client.session
        session["mfa_verified"] = True
        session["security_posture_review_nagged"] = True
        session.save()
        self.school = School.objects.create(
            name="Cedar School", slug="cedar-sv", subdomain="cedar-sv",
            is_active=False, country_code="US", settings={},
        )
        self.verif = SignupVerification.objects.create(
            school=self.school, email="owner@cedar.test",
            expires_at=timezone.now() - timedelta(days=1),  # expired
        )

    def test_console_lists_pending_signup(self):
        resp = self.client.get(reverse("super:signup_verifications"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "owner@cedar.test")
        self.assertContains(resp, "Cedar School")

    def test_resend_extends_expiry_keeps_token(self):
        old_token = self.verif.token
        with mock.patch(
            "apps.schools.super_views_signup_verifications._send_signup_verification_email"
        ) as send:
            resp = self.client.post(
                reverse("super:signup_verification_action", args=[self.verif.pk]),
                {"action": "resend"}, HTTP_HOST=HOST,
            )
        self.assertEqual(resp.status_code, 302)
        self.verif.refresh_from_db()
        self.assertEqual(self.verif.token, old_token)  # resend keeps token
        self.assertGreater(self.verif.expires_at, timezone.now())  # expiry refreshed
        send.assert_called_once()

    def test_regenerate_rotates_token_and_extends(self):
        old_token = self.verif.token
        with mock.patch(
            "apps.schools.super_views_signup_verifications._send_signup_verification_email"
        ) as send:
            resp = self.client.post(
                reverse("super:signup_verification_action", args=[self.verif.pk]),
                {"action": "regenerate"}, HTTP_HOST=HOST,
            )
        self.assertEqual(resp.status_code, 302)
        self.verif.refresh_from_db()
        self.assertNotEqual(self.verif.token, old_token)  # token rotated
        self.assertGreater(self.verif.expires_at, timezone.now())
        send.assert_called_once()

    def test_verified_signup_is_not_resent(self):
        self.verif.verified_at = timezone.now()
        self.verif.save(update_fields=["verified_at"])
        with mock.patch(
            "apps.schools.super_views_signup_verifications._send_signup_verification_email"
        ) as send:
            resp = self.client.post(
                reverse("super:signup_verification_action", args=[self.verif.pk]),
                {"action": "resend"}, HTTP_HOST=HOST,
            )
        self.assertEqual(resp.status_code, 302)
        send.assert_not_called()
