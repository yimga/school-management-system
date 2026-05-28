"""MFA UI context for manager operator header icon."""

from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.accounts.mfa_ui_context import build_mfa_ui_context, operator_mfa_context


class MfaUiContextTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_non_manager_host_returns_defaults(self):
        request = self.factory.get("/super/")
        request.user = MagicMock(is_authenticated=True, is_staff=True)
        request.public_host_kind = "tenant"
        ctx = build_mfa_ui_context(request)
        self.assertFalse(ctx["show_mfa_header_icon"])
        self.assertFalse(ctx["mfa_enrolled"])

    def test_manager_staff_without_device_shows_setup_icon(self):
        request = self.factory.get("/super/")
        request.user = MagicMock(is_authenticated=True, is_staff=True)
        request.public_host_kind = "manager"
        with patch("django_otp.user_has_device", return_value=False):
            ctx = build_mfa_ui_context(request)
        self.assertTrue(ctx["show_mfa_header_icon"])
        self.assertTrue(ctx["mfa_setup_needed"])
        self.assertFalse(ctx["mfa_enrolled"])
        self.assertFalse(ctx["show_mfa_banner"])
        self.assertIn("/authentication/mfa/", ctx["mfa_setup_url"])

    def test_manager_staff_with_device_shows_enrolled(self):
        request = self.factory.get("/admin/")
        request.user = MagicMock(is_authenticated=True, is_staff=True)
        request.public_host_kind = "manager"
        with patch("django_otp.user_has_device", return_value=True):
            ctx = operator_mfa_context(request)
        self.assertTrue(ctx["show_mfa_header_icon"])
        self.assertTrue(ctx["mfa_enrolled"])
        self.assertFalse(ctx["mfa_setup_needed"])
