"""Tests for tenant-configurable MFA enforcement modes (strict / grace / optional).

Covers the pure resolver (``apps.accounts.mfa_defaults.resolve_mfa_enforcement``)
and its integration in ``RequireMFAMiddleware`` — proving that the platform
default stays a hard wall (strict) while grace/optional let a required user
through with a nudge instead of a first-click redirect.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.middleware import RequireMFAMiddleware
from apps.accounts.mfa_defaults import (
    DEFAULT_MFA_GRACE_PERIOD_DAYS,
    normalize_mfa_mode,
    resolve_mfa_enforcement,
)

User = get_user_model()


def _ok(request):
    return HttpResponse("ok")


class NormalizeMfaModeTests(TestCase):
    def test_known_modes_pass_through(self):
        self.assertEqual(normalize_mfa_mode("strict"), "strict")
        self.assertEqual(normalize_mfa_mode("grace"), "grace")
        self.assertEqual(normalize_mfa_mode("optional"), "optional")

    def test_blank_and_unknown_default_to_strict(self):
        self.assertEqual(normalize_mfa_mode(None), "strict")
        self.assertEqual(normalize_mfa_mode(""), "strict")
        self.assertEqual(normalize_mfa_mode("nonsense"), "strict")
        self.assertEqual(normalize_mfa_mode("GRACE "), "grace")  # trimmed + lowered


class ResolveMfaEnforcementTests(TestCase):
    def _user(self, *, days_ago=0):
        return SimpleNamespace(
            date_joined=timezone.now() - timedelta(days=days_ago)
        )

    def test_not_required_is_noop(self):
        d = resolve_mfa_enforcement(
            must_have_mfa=False, has_device=False, mode="strict", user=self._user()
        )
        self.assertEqual(d.action, "none")

    def test_has_device_is_noop(self):
        d = resolve_mfa_enforcement(
            must_have_mfa=True, has_device=True, mode="strict", user=self._user()
        )
        self.assertEqual(d.action, "none")

    def test_strict_required_no_device_enforces(self):
        d = resolve_mfa_enforcement(
            must_have_mfa=True, has_device=False, mode="strict", user=self._user()
        )
        self.assertEqual(d.action, "enforce")

    def test_optional_required_no_device_nudges(self):
        d = resolve_mfa_enforcement(
            must_have_mfa=True, has_device=False, mode="optional", user=self._user()
        )
        self.assertEqual(d.action, "nudge")

    def test_grace_within_window_grants(self):
        d = resolve_mfa_enforcement(
            must_have_mfa=True,
            has_device=False,
            mode="grace",
            grace_period_days=7,
            user=self._user(days_ago=1),
        )
        self.assertEqual(d.action, "grace")
        self.assertGreaterEqual(d.grace_days_remaining, 5)

    def test_grace_past_window_enforces(self):
        d = resolve_mfa_enforcement(
            must_have_mfa=True,
            has_device=False,
            mode="grace",
            grace_period_days=7,
            user=self._user(days_ago=30),
        )
        self.assertEqual(d.action, "enforce")

    def test_grace_blank_days_uses_default(self):
        # days_ago between default and a larger window proves the default applies.
        d = resolve_mfa_enforcement(
            must_have_mfa=True,
            has_device=False,
            mode="grace",
            grace_period_days=None,
            user=self._user(days_ago=DEFAULT_MFA_GRACE_PERIOD_DAYS - 1),
        )
        self.assertEqual(d.action, "grace")

    def test_grace_without_anchor_is_lenient(self):
        d = resolve_mfa_enforcement(
            must_have_mfa=True,
            has_device=False,
            mode="grace",
            grace_period_days=7,
            user=SimpleNamespace(),  # no date_joined
        )
        self.assertEqual(d.action, "grace")


class RequireMfaModeMiddlewareTests(TestCase):
    """End-to-end through RequireMFAMiddleware with a mocked effective site."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="mode-owner",
            email="mode-owner@example.com",
            password="password",
            role="ADMIN",
            is_staff=True,
        )

    def _run_with_site(self, path, *, mode, days_ago=0):
        # Anchor the user's grace window.
        self.user.date_joined = timezone.now() - timedelta(days=days_ago)
        self.user.save(update_fields=["date_joined"])
        site = mock.Mock(
            require_mfa_all_staff=True,
            require_mfa_roles=[],
            mfa_enforcement_mode=mode,
            mfa_grace_period_days=7,
        )
        with mock.patch(
            "apps.accounts.middleware.get_effective_site_settings",
            return_value=site,
        ):
            request = self.factory.get(path)
            request.user = self.user
            request.session = {}
            return RequireMFAMiddleware(_ok)(request)

    def test_strict_still_hard_walls(self):
        resp = self._run_with_site("/portal/", mode="strict")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/mfa/setup", resp.url)
        self.assertIn("legacy=1", resp.url)  # routes to the polished page

    def test_optional_lets_through_with_nudge(self):
        resp = self._run_with_site("/portal/", mode="optional")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

    def test_grace_within_window_lets_through(self):
        resp = self._run_with_site("/portal/", mode="grace", days_ago=1)
        self.assertEqual(resp.status_code, 200)

    def test_grace_past_window_hard_walls(self):
        resp = self._run_with_site("/portal/", mode="grace", days_ago=30)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/mfa/setup", resp.url)

    def test_mfa_policy_page_reachable_while_strict_walled(self):
        # Catch-22 guard: even in strict mode, a required no-device admin must
        # reach the policy page (where they switch to grace/optional) instead of
        # being bounced to setup — otherwise the toggle is unreachable.
        resp = self._run_with_site("/portal/security/mfa-policy/", mode="strict")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

    def test_sw_reset_reachable_while_strict_walled(self):
        # The service-worker reset escape hatch must always work, even for a
        # required no-device user behind the strict wall (it only clears the
        # browser's stale SW/caches).
        resp = self._run_with_site("/sw-reset/", mode="strict")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

    def test_optional_sets_nudge_attribute(self):
        self.user.date_joined = timezone.now()
        self.user.save(update_fields=["date_joined"])
        site = mock.Mock(
            require_mfa_all_staff=True,
            require_mfa_roles=[],
            mfa_enforcement_mode="optional",
            mfa_grace_period_days=7,
        )
        with mock.patch(
            "apps.accounts.middleware.get_effective_site_settings",
            return_value=site,
        ):
            request = self.factory.get("/portal/")
            request.user = self.user
            request.session = {}
            RequireMFAMiddleware(_ok)(request)
            self.assertTrue(getattr(request, "rmc_mfa_nudge", None))
            self.assertEqual(request.rmc_mfa_nudge["action"], "nudge")
