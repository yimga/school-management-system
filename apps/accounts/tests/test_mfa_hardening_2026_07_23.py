"""MFA hardening — audit remediation 2026-07-23.

Each test FIRES against the pre-fix code (fails there), so it proves the fix
rather than merely passing:

* M1 — logout revokes the durable device-trust cookie (it used to survive a
  plain logout for up to 30 days, so the next person to sign in on a shared
  browser skipped MFA).
* M2 — a wrong TOTP during enrollment re-renders WITH the QR/secret/device_id
  preserved instead of throwing them away and bouncing to step 1.
* M3 — a StaticDevice (backup codes) alone does NOT count as an MFA device
  (django_otp's user_has_device would include it, walling a backup-codes-only
  user in a verify<->setup bounce).
* M4 — a non-numeric device_id does not 500 (the ORM's int coercion ValueError).
"""

from __future__ import annotations

from importlib import import_module

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.mfa_device_trust import DEVICE_TRUST_COOKIE, issue_device_trust_token

User = get_user_model()


def _fresh_session():
    return import_module(django_settings.SESSION_ENGINE).SessionStore()


def _post(factory, path, data, user):
    request = factory.post(path, data)
    request.user = user
    request.session = _fresh_session()
    request._messages = FallbackStorage(request)
    return request


class MfaPresenceExcludesStaticDeviceTests(TestCase):
    """M3: backup codes alone are not 'MFA enrolled'."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="m3", email="m3@example.com", password="pass12345678"
        )

    def test_static_device_only_is_not_a_device(self):
        from apps.accounts.mfa_setup_flow import mfa_has_device
        from apps.accounts.post_login_mfa import _user_has_mfa_device

        StaticDevice.objects.create(user=self.user, name="backup", confirmed=True)
        self.assertFalse(
            mfa_has_device(self.user),
            "a StaticDevice (backup codes) must not count as an MFA device",
        )
        self.assertFalse(
            _user_has_mfa_device(self.user),
            "post-login presence check must also exclude StaticDevice",
        )

    def test_confirmed_totp_is_a_device(self):
        from apps.accounts.mfa_setup_flow import mfa_has_device
        from apps.accounts.post_login_mfa import _user_has_mfa_device

        TOTPDevice.objects.create(user=self.user, name="default", confirmed=True)
        self.assertTrue(mfa_has_device(self.user))
        self.assertTrue(_user_has_mfa_device(self.user))

    def test_unconfirmed_totp_is_not_a_device(self):
        from apps.accounts.mfa_setup_flow import mfa_has_device

        TOTPDevice.objects.create(user=self.user, name="default", confirmed=False)
        self.assertFalse(mfa_has_device(self.user))


class MfaEnrollInvalidTokenTests(TestCase):
    """M2 + M4: enrollment resilience on bad input."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="m2", email="m2@example.com", password="pass12345678"
        )

    def test_wrong_token_preserves_qr_and_device(self):
        from apps.accounts.mfa_setup_flow import handle_mfa_setup_post

        device = TOTPDevice.objects.create(
            user=self.user, name="default", confirmed=False
        )
        request = _post(
            self.factory,
            "/mfa/setup/",
            {"verify_token": "1", "device_id": str(device.id), "token": "000000"},
            self.user,
        )
        outcome, ctx = handle_mfa_setup_post(request)
        self.assertEqual(outcome, "render")
        self.assertIsNotNone(
            ctx.get("qr_code"),
            "a mistyped code threw the QR away and bounced the user to step 1",
        )
        self.assertEqual(ctx.get("device_id"), device.id)
        device.refresh_from_db()
        self.assertFalse(device.confirmed)  # a wrong code must not confirm

    def test_non_numeric_device_id_does_not_500(self):
        from apps.accounts.mfa_setup_flow import handle_mfa_setup_post

        request = _post(
            self.factory,
            "/mfa/setup/",
            {"verify_token": "1", "device_id": "not-a-number", "token": "000000"},
            self.user,
        )
        # Pre-fix: TOTPDevice.objects.get(id="not-a-number") raised ValueError.
        outcome, ctx = handle_mfa_setup_post(request)
        self.assertEqual(outcome, "render")


class LogoutRevokesDeviceTrustTests(TestCase):
    """M1: a plain logout clears the durable trust cookie."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="m1", email="m1@example.com", password="pass12345678"
        )

    def test_logout_deletes_the_trust_cookie(self):
        self.client.force_login(self.user)
        self.client.cookies[DEVICE_TRUST_COOKIE] = issue_device_trust_token(self.user)
        response = self.client.get(reverse("accounts:logout"))
        self.assertIn(
            DEVICE_TRUST_COOKIE,
            response.cookies,
            "logout must emit a Set-Cookie that clears the device-trust cookie",
        )
        morsel = response.cookies[DEVICE_TRUST_COOKIE]
        # A deletion is an empty value with an immediate/past expiry (max-age 0).
        self.assertEqual(morsel.value, "")
        self.assertIn(str(morsel["max-age"]), ("0", ""))
