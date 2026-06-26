"""Tests for immersive login context builder."""

from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.accounts.login_immersive_context import build_login_immersive_context
from apps.accounts.views import login_view


class LoginImmersiveContextTests(SimpleTestCase):
    def test_build_returns_required_keys(self):
        request = RequestFactory().get("/authentication/login/")
        payload = build_login_immersive_context(request)
        for key in (
            "ticker_items",
            "carousel_slides",
            "bento_stats",
            "dash_feed",
            "moments",
            "clock_label",
            "date_label",
        ):
            self.assertIn(key, payload)
        self.assertTrue(payload["ticker_items"])
        self.assertTrue(payload["moments"])
        self.assertEqual(len(payload["moments"]), 3)

    def test_post_role_defaults_without_query_params(self):
        request = RequestFactory().get("/authentication/login/")
        request.school = None
        request.user = type("U", (), {"is_authenticated": False})()
        request.session = {}
        request.public_host_kind = None
        request.META = {
            "REMOTE_ADDR": "127.0.0.1",
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
        }

        with patch("apps.accounts.views.render") as mock_render:
            login_view(request)
            context = mock_render.call_args[0][2]
        self.assertEqual(context["post_role"], "staff")
