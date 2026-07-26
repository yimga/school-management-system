"""Auth-shell fast path: login pages skip portal sidebar builder."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.siteconfig.context_processors import site_settings


# site_settings is a DB-touching context processor: beyond the three mocked
# helpers it also reads the RuntimeDefaults singleton (public brand palette,
# context_processors.py:1193) — a legitimate hot-path query. Run DB-backed +
# isolated (TestCase) rather than SimpleTestCase, which forbids that read.
class AuthShellFastPathTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    @mock.patch("apps.siteconfig.context_processors._get_portal_sidebar_items")
    @mock.patch("apps.siteconfig.context_processors.get_effective_site_settings")
    @mock.patch("apps.siteconfig.context_processors.build_platform_default_site_settings")
    def test_login_skips_sidebar_builder(
        self, mock_default_site, mock_effective, mock_sidebar
    ):
        # site_settings runs the full theme/logo context for every path (it only
        # skips the *sidebar builder* on the auth-shell fast path), calling
        # setattr(site, "is_preview", ...) + site.get_theme_background(...) etc. In
        # production `site` is a real SiteSettings / build_platform_default_site_settings()
        # (has __dict__ + those methods); a bare object() has neither, so use a
        # MagicMock that supports arbitrary attribute-set + method calls.
        mock_effective.return_value = mock_default_site.return_value = mock.MagicMock()
        request = self.rf.get("/authentication/login/")
        request.user = AnonymousUser()
        request.session = {}

        ctx = site_settings(request)

        mock_sidebar.assert_not_called()
        self.assertEqual(ctx["PORTAL_SIDEBAR_ITEMS"], [])
        self.assertEqual(ctx.get("copilot_pending_approvals_count", 0), 0)

    @mock.patch("apps.siteconfig.context_processors._get_portal_sidebar_items")
    @mock.patch("apps.siteconfig.context_processors.get_effective_site_settings")
    @mock.patch("apps.siteconfig.context_processors.build_platform_default_site_settings")
    def test_portal_still_builds_sidebar(
        self, mock_default_site, mock_effective, mock_sidebar
    ):
        # site_settings runs the full theme/logo context for every path (it only
        # skips the *sidebar builder* on the auth-shell fast path), calling
        # setattr(site, "is_preview", ...) + site.get_theme_background(...) etc. In
        # production `site` is a real SiteSettings / build_platform_default_site_settings()
        # (has __dict__ + those methods); a bare object() has neither, so use a
        # MagicMock that supports arbitrary attribute-set + method calls.
        mock_effective.return_value = mock_default_site.return_value = mock.MagicMock()
        mock_sidebar.return_value = [{"id": "home"}]
        request = self.rf.get("/portal/parent/")
        request.user = AnonymousUser()
        request.session = {}

        ctx = site_settings(request)

        mock_sidebar.assert_called_once()
        self.assertEqual(ctx["PORTAL_SIDEBAR_ITEMS"], [{"id": "home"}])
