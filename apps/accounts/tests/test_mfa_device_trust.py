"""Durable MFA device-trust cookie: signed, user-bound, password-revocable.

Locks the contract that makes "trust this device" survive a session reset without
becoming a forgeable MFA bypass: a valid cookie verifies only for the right user
with the current password fingerprint, and the MFA middleware honours it (and
re-establishes the session flag) so a flushed session isn't re-prompted.
"""
from __future__ import annotations

from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.middleware import RequireMFAMiddleware
from apps.accounts.mfa_device_trust import (
    DEVICE_TRUST_COOKIE,
    clear_device_trust_cookie,
    device_trust_valid,
    issue_device_trust_token,
    set_device_trust_cookie,
)
from apps.accounts.models import User


class DeviceTrustModuleTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="trust-user", email="t@example.com", password="pass12345678"
        )

    def _req_with_cookie(self, token):
        request = self.factory.get("/portal/dashboard/")
        request.COOKIES[DEVICE_TRUST_COOKIE] = token
        return request

    def test_round_trip_valid(self):
        token = issue_device_trust_token(self.user)
        self.assertTrue(device_trust_valid(self._req_with_cookie(token), self.user))

    def test_no_cookie_is_invalid(self):
        self.assertFalse(
            device_trust_valid(self.factory.get("/portal/dashboard/"), self.user)
        )

    def test_wrong_user_is_invalid(self):
        other = User.objects.create_user(
            username="other", email="o@example.com", password="pass12345678"
        )
        token = issue_device_trust_token(self.user)
        self.assertFalse(device_trust_valid(self._req_with_cookie(token), other))

    def test_password_change_revokes(self):
        token = issue_device_trust_token(self.user)
        # Password change rotates get_session_auth_hash -> fingerprint mismatch.
        self.user.set_password("brand-new-pass-98765")
        self.user.save(update_fields=["password"])
        self.assertFalse(device_trust_valid(self._req_with_cookie(token), self.user))

    def test_tampered_token_is_invalid(self):
        token = issue_device_trust_token(self.user)
        tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
        self.assertFalse(device_trust_valid(self._req_with_cookie(tampered), self.user))

    def test_anonymous_user_is_invalid(self):
        from django.contrib.auth.models import AnonymousUser

        token = issue_device_trust_token(self.user)
        self.assertFalse(
            device_trust_valid(self._req_with_cookie(token), AnonymousUser())
        )
        self.assertFalse(device_trust_valid(self._req_with_cookie(token), None))

    def test_set_cookie_marks_httponly_and_max_age(self):
        from django.http import HttpResponse

        response = HttpResponse()
        request = self.factory.get("/")
        set_device_trust_cookie(response, self.user, request)
        cookie = response.cookies[DEVICE_TRUST_COOKIE]
        self.assertTrue(cookie["httponly"])
        self.assertGreater(int(cookie["max-age"]), 0)
        self.assertEqual(cookie["samesite"], "Lax")

    @override_settings(SESSION_COOKIE_DOMAIN=".runmycampus.com")
    def test_set_cookie_matches_session_cookie_domain(self):
        """Trust cookie must share the session domain or tenant-subdomain MFA re-prompts."""
        from django.http import HttpResponse

        response = HttpResponse()
        request = self.factory.get("/")
        set_device_trust_cookie(response, self.user, request)
        cookie = response.cookies[DEVICE_TRUST_COOKIE]
        self.assertEqual(cookie["domain"], ".runmycampus.com")

    @override_settings(SESSION_COOKIE_DOMAIN=".runmycampus.com")
    def test_clear_cookie_uses_same_domain(self):
        from django.http import HttpResponse

        response = HttpResponse()
        set_device_trust_cookie(response, self.user, self.factory.get("/"))
        clear_device_trust_cookie(response)
        # Morsel after delete still exposes the domain used for Set-Cookie clear.
        cleared = response.cookies[DEVICE_TRUST_COOKIE]
        self.assertEqual(cleared["domain"], ".runmycampus.com")
        # Django may encode max-age as 0 or empty depending on version; expires is past.
        self.assertTrue(
            cleared["max-age"] in ("0", 0, "") or int(cleared.get("max-age") or 0) == 0
        )


class ApplyDeviceTrustOnEnrollTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="enroll-trust", email="e@example.com", password="pass12345678"
        )

    def _req(self, *, remember="1"):
        request = self.factory.post(
            "/authentication/onboarding/mfa/",
            data={"verify_token": "123456", "remember_device": remember},
        )
        request.user = self.user
        request.session = {}
        return request

    def test_enroll_confirm_with_remember_sets_session_and_cookie(self):
        from django.http import HttpResponse

        from apps.accounts.mfa_setup_flow import apply_device_trust_on_enroll

        request = self._req(remember="1")
        response = HttpResponse()
        apply_device_trust_on_enroll(request, response)
        self.assertTrue(request.session.get("mfa_verified"))
        self.assertIn("mfa_verified_until", request.session)
        self.assertIn(DEVICE_TRUST_COOKIE, response.cookies)

    def test_enroll_without_remember_skips_trust(self):
        from django.http import HttpResponse

        from apps.accounts.mfa_setup_flow import apply_device_trust_on_enroll

        request = self._req(remember="0")
        response = HttpResponse()
        apply_device_trust_on_enroll(request, response)
        self.assertFalse(request.session.get("mfa_verified"))
        self.assertNotIn(DEVICE_TRUST_COOKIE, response.cookies)

    def test_non_verify_post_skips_trust(self):
        from django.http import HttpResponse

        from apps.accounts.mfa_setup_flow import apply_device_trust_on_enroll

        request = self.factory.post(
            "/authentication/onboarding/mfa/",
            data={"regen_backup": "1", "remember_device": "1"},
        )
        request.user = self.user
        request.session = {}
        response = HttpResponse()
        apply_device_trust_on_enroll(request, response)
        self.assertFalse(request.session.get("mfa_verified"))
        self.assertNotIn(DEVICE_TRUST_COOKIE, response.cookies)


class DeviceTrustMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="mw-user", email="mw@example.com", password="pass12345678"
        )

    def _req(self, *, cookie=None):
        request = self.factory.get("/portal/dashboard/")
        request.user = self.user
        request.session = {}
        if cookie:
            request.COOKIES[DEVICE_TRUST_COOKIE] = cookie
        return request

    def test_valid_cookie_verifies_and_rehydrates_session(self):
        request = self._req(cookie=issue_device_trust_token(self.user))
        self.assertTrue(RequireMFAMiddleware._is_mfa_verified(request))
        # The durable cookie re-establishes the session flag for the rest of the session.
        self.assertTrue(request.session.get("mfa_verified"))

    def test_no_cookie_is_not_verified(self):
        request = self._req()
        self.assertFalse(RequireMFAMiddleware._is_mfa_verified(request))

    def test_session_flag_still_wins_without_cookie(self):
        request = self._req()
        request.session["mfa_verified"] = True
        self.assertTrue(RequireMFAMiddleware._is_mfa_verified(request))
