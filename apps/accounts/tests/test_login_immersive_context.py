"""Tests for immersive login context builder."""

from django.test import RequestFactory, SimpleTestCase

from apps.accounts.login_immersive_context import build_login_immersive_context


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
