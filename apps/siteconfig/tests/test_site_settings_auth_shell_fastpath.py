"""Auth-shell fast path: login pages skip portal sidebar builder."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.context_processors import site_settings


class AuthShellFastPathTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    @mock.patch("apps.siteconfig.context_processors._get_portal_sidebar_items")
    @mock.patch("apps.siteconfig.context_processors.get_effective_site_settings")
    @mock.patch("apps.siteconfig.context_processors.build_platform_default_site_settings")
    def test_login_skips_sidebar_builder(
        self, mock_default_site, mock_effective, mock_sidebar
    ):
        mock_effective.return_value = mock_default_site.return_value = object()
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
        mock_effective.return_value = mock_default_site.return_value = object()
        mock_sidebar.return_value = [{"id": "home"}]
        request = self.rf.get("/portal/parent/")
        request.user = AnonymousUser()
        request.session = {}

        ctx = site_settings(request)

        mock_sidebar.assert_called_once()
        self.assertEqual(ctx["PORTAL_SIDEBAR_ITEMS"], [{"id": "home"}])
