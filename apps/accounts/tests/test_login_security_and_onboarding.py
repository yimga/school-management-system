"""Login bot/brute-force defense + signup onboarding-link tests (2026-06-08).

Covers:
- ``apps.accounts.turnstile`` — env-gated, fail-open-on-outage, fail-closed-on-bad-token.
- ``apps.accounts.login_guard`` — always-on cache lockout (threshold, clear, fail-open, per-user).
- ``LegacySetupView`` — honors a safe same-host ``?next=`` via the session, post-reset auto-login.
- Welcome-email template — surfaces the one-time set-password link, falls back to the portal URL.
- ``build_provision_setup_password_url`` — carries ``next`` through.
"""

from __future__ import annotations

from unittest import mock

import requests
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings


class TurnstileTests(SimpleTestCase):
    @override_settings(TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY="")
    def test_disabled_is_inert(self):
        from apps.accounts.turnstile import turnstile_enabled, verify_turnstile

        self.assertFalse(turnstile_enabled())
        # Not configured → never blocks sign-in.
        self.assertTrue(verify_turnstile("anything"))

    @override_settings(TURNSTILE_SITE_KEY="site", TURNSTILE_SECRET_KEY="secret")
    def test_enabled_requires_a_token(self):
        from apps.accounts.turnstile import turnstile_enabled, verify_turnstile

        self.assertTrue(turnstile_enabled())
        self.assertFalse(verify_turnstile(""))

    @override_settings(TURNSTILE_SITE_KEY="site", TURNSTILE_SECRET_KEY="secret")
    @mock.patch("apps.accounts.turnstile.requests.post")
    def test_valid_token_passes(self, m_post):
        m_post.return_value.json.return_value = {"success": True}
        from apps.accounts.turnstile import verify_turnstile

        self.assertTrue(verify_turnstile("good-token"))

    @override_settings(TURNSTILE_SITE_KEY="site", TURNSTILE_SECRET_KEY="secret")
    @mock.patch("apps.accounts.turnstile.requests.post")
    def test_invalid_token_fails_closed(self, m_post):
        m_post.return_value.json.return_value = {"success": False}
        from apps.accounts.turnstile import verify_turnstile

        self.assertFalse(verify_turnstile("bad-token"))

    @override_settings(TURNSTILE_SITE_KEY="site", TURNSTILE_SECRET_KEY="secret")
    @mock.patch(
        "apps.accounts.turnstile.requests.post",
        side_effect=requests.RequestException("cloudflare down"),
    )
    def test_outage_fails_open(self, _m_post):
        # A Cloudflare outage must not lock every legitimate user out.
        from apps.accounts.turnstile import verify_turnstile

        self.assertTrue(verify_turnstile("token"))


class LoginGuardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def _req(self, ip="203.0.113.5"):
        return self.rf.post("/authentication/login/", REMOTE_ADDR=ip)

    @override_settings(
        LOGIN_LOCKOUT_ENABLED=True,
        LOGIN_LOCKOUT_THRESHOLD=3,
        LOGIN_LOCKOUT_COOLOFF_SECONDS=900,
    )
    def test_locks_after_threshold(self):
        from apps.accounts import login_guard

        req = self._req()
        for _ in range(3):
            self.assertFalse(login_guard.lockout_state(req, "bob")[0])
            login_guard.record_failed_attempt(req, "bob")
        locked, retry_after = login_guard.lockout_state(req, "bob")
        self.assertTrue(locked)
        self.assertEqual(retry_after, 900)

    @override_settings(LOGIN_LOCKOUT_ENABLED=True, LOGIN_LOCKOUT_THRESHOLD=2)
    def test_clear_resets(self):
        from apps.accounts import login_guard

        req = self._req()
        login_guard.record_failed_attempt(req, "bob")
        login_guard.record_failed_attempt(req, "bob")
        self.assertTrue(login_guard.lockout_state(req, "bob")[0])
        login_guard.clear_attempts(req, "bob")
        self.assertFalse(login_guard.lockout_state(req, "bob")[0])

    @override_settings(LOGIN_LOCKOUT_ENABLED=True, LOGIN_LOCKOUT_THRESHOLD=2)
    def test_per_username_isolation(self):
        from apps.accounts import login_guard

        req = self._req()
        login_guard.record_failed_attempt(req, "bob")
        login_guard.record_failed_attempt(req, "bob")
        self.assertTrue(login_guard.lockout_state(req, "bob")[0])
        # A different username from the same IP is unaffected.
        self.assertFalse(login_guard.lockout_state(req, "alice")[0])

    @override_settings(LOGIN_LOCKOUT_ENABLED=False, LOGIN_LOCKOUT_THRESHOLD=1)
    def test_disabled_never_locks(self):
        from apps.accounts import login_guard

        req = self._req()
        login_guard.record_failed_attempt(req, "bob")
        login_guard.record_failed_attempt(req, "bob")
        self.assertFalse(login_guard.lockout_state(req, "bob")[0])

    @override_settings(LOGIN_LOCKOUT_ENABLED=True, LOGIN_LOCKOUT_THRESHOLD=1)
    def test_fails_open_on_cache_error(self):
        from apps.accounts import login_guard

        req = self._req()
        with mock.patch(
            "apps.accounts.login_guard.cache.get", side_effect=RuntimeError("down")
        ):
            self.assertEqual(login_guard.lockout_state(req, "bob"), (False, 0))


class LegacySetupNextTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _view_with_session(self, session):
        from apps.accounts.views_legacy_setup import LegacySetupView

        req = self.rf.get("/authentication/legacy-setup/uid/token/")
        req.session = session
        view = LegacySetupView()
        view.request = req
        return view

    def test_post_reset_auto_login_configured(self):
        from apps.accounts.views_legacy_setup import LegacySetupView

        self.assertTrue(LegacySetupView.post_reset_login)
        self.assertEqual(
            LegacySetupView.post_reset_login_backend,
            "django.contrib.auth.backends.ModelBackend",
        )

    def test_success_url_honors_safe_relative_next(self):
        view = self._view_with_session({"legacy_setup_next": "/backend/"})
        self.assertEqual(view.get_success_url(), "/backend/")

    def test_success_url_rejects_offsite_next(self):
        view = self._view_with_session({"legacy_setup_next": "https://evil.example/x"})
        # Falls back to the configured login success_url.
        self.assertNotIn("evil.example", view.get_success_url())

    def test_success_url_default_without_next(self):
        view = self._view_with_session({})
        self.assertTrue(view.get_success_url())


class WelcomeEmailSetupLinkTests(SimpleTestCase):
    def test_html_surfaces_setup_link(self):
        out = render_to_string(
            "emails/tenant_admin_signup_completed.html",
            {"school_name": "Gilead Tech", "setup_password_url": "https://t.example/set"},
        )
        self.assertIn("https://t.example/set", out)
        self.assertIn("Set your password", out)

    def test_html_falls_back_to_portal_without_setup_link(self):
        out = render_to_string(
            "emails/tenant_admin_signup_completed.html",
            {"school_name": "Gilead Tech", "portal_url": "https://portal.example/"},
        )
        self.assertIn("https://portal.example/", out)
        self.assertIn("Open your portal", out)

    def test_txt_surfaces_setup_link(self):
        out = render_to_string(
            "emails/tenant_admin_signup_completed.txt",
            {"school_name": "Gilead Tech", "setup_password_url": "https://t.example/set"},
        )
        self.assertIn("https://t.example/set", out)


class ProvisionSetupUrlTests(SimpleTestCase):
    @mock.patch(
        "apps.schools.provision_email_urls.default_token_generator.make_token",
        return_value="tok",
    )
    @mock.patch(
        "apps.schools.provision_email_urls.build_tenant_authentication_url",
        return_value="https://acme.runmycampus.com/authentication/legacy-setup/uid/token/",
    )
    @mock.patch(
        "apps.schools.provision_email_urls.reverse",
        return_value="/authentication/legacy-setup/uid/token/",
    )
    def test_next_path_is_appended(self, _m_reverse, _m_build, _m_token):
        from apps.schools.provision_email_urls import build_provision_setup_password_url

        user = mock.Mock(pk=7)
        url = build_provision_setup_password_url(
            object(), user, next_path="/backend/provisioning/"
        )
        self.assertIn("next=%2Fbackend%2Fprovisioning%2F", url)

    @mock.patch(
        "apps.schools.provision_email_urls.default_token_generator.make_token",
        return_value="tok",
    )
    @mock.patch(
        "apps.schools.provision_email_urls.build_tenant_authentication_url",
        return_value="https://acme.runmycampus.com/authentication/legacy-setup/uid/token/",
    )
    @mock.patch(
        "apps.schools.provision_email_urls.reverse",
        return_value="/authentication/legacy-setup/uid/token/",
    )
    def test_no_next_path_leaves_url_clean(self, _m_reverse, _m_build, _m_token):
        from apps.schools.provision_email_urls import build_provision_setup_password_url

        user = mock.Mock(pk=7)
        url = build_provision_setup_password_url(object(), user)
        self.assertNotIn("next=", url)


class CspTurnstileTests(SimpleTestCase):
    @override_settings(TURNSTILE_SITE_KEY="")
    def test_no_cloudflare_when_disabled(self):
        from apps.security.csp_middleware import _build_policy

        policy = _build_policy(nonce="abc")
        self.assertNotIn("challenges.cloudflare.com", policy)

    @override_settings(TURNSTILE_SITE_KEY="site")
    def test_cloudflare_allowed_when_enabled(self):
        from apps.security.csp_middleware import _build_policy

        policy = _build_policy(nonce="abc")
        self.assertIn("https://challenges.cloudflare.com", policy)
        # Turnstile renders inside an iframe → frame-src must allow it too.
        self.assertIn("frame-src", policy)
