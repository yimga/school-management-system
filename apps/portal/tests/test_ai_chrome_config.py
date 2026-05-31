"""AI chrome configurability — tenant flags and URL resolution."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from unittest.mock import patch

from apps.portal.ai_chrome_config import (
    ai_copilot_query_api_enabled_for_request,
    resolve_ai_chrome_config,
)
from apps.portal.help_governance import parent_student_help_surface_policy

UserModel = get_user_model()


class AIChromeConfigTests(SimpleTestCase):
    def test_parent_policy_reads_defaults_without_request(self):
        policy = parent_student_help_surface_policy()
        self.assertFalse(policy["ai_assistant_panel"])
        self.assertTrue(policy["support_deflection_on_submit"])

    @patch("apps.schools.control_plane.user_has_control_plane_access", return_value=False)
    @patch(
        "apps.portal.ai_chrome_config.parent_student_help_surface_policy",
        return_value={"ai_assistant_panel": False},
    )
    @patch("apps.portal.ai_chrome_config._manager_rail_enabled", return_value=False)
    @patch("apps.portal.ai_chrome_config._provider_status")
    @patch("apps.portal.ai_chrome_config._effective_flags", return_value={})
    @patch("apps.portal.ai_chrome_config.ai_assistant_panel_enabled_for_request", return_value=True)
    @patch("apps.portal.ai_chrome_config.ai_help_enabled_for_request", return_value=True)
    def test_resolve_includes_url_keys(
        self, _help, _panel, _flags, _status, _rail, _policy, _cp
    ):
        _status.return_value = {"rules_fallback_enabled": True, "reachable": False}
        request = RequestFactory().get("/authentication/backend/")
        request.user = UserModel(username="t1", role="TEACHER")
        request.public_host_kind = "tenant"
        cfg = resolve_ai_chrome_config(request)
        self.assertIn("urls", cfg)
        self.assertIn("features", cfg)
        self.assertIn("copilot_query", cfg["urls"])
        self.assertIn("health", cfg["urls"])


class AIChromeConfigDBTests(TestCase):
    def test_query_api_enabled_default_true(self):
        request = RequestFactory().get("/")
        request.user = UserModel.objects.create_user(
            username="a1chrome",
            password="Test1234!",
            role="ADMIN",
        )
        self.assertTrue(ai_copilot_query_api_enabled_for_request(request))
