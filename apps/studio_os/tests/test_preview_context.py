"""
§5.6 Live Previews: tests for get_studio_preview_context (impact_summary, dependency_warnings).
Uses SimpleTestCase so no DB is created — avoids migration conflicts in test env.
"""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.studio_os.services import get_studio_preview_context, get_studio_preview_url


class StudioPreviewContextTests(SimpleTestCase):
    """get_studio_preview_context returns launch context when mode=launch and school is set."""

    def test_preview_context_empty_for_non_launch_mode(self):
        request = Mock()
        request.school = None
        out = get_studio_preview_context("experience", request)
        self.assertEqual(out, {})
        out = get_studio_preview_context("output", request)
        self.assertEqual(out, {})

    def test_preview_context_empty_when_no_school(self):
        request = Mock()
        request.school = None
        out = get_studio_preview_context("launch", request)
        self.assertEqual(out, {})

    def test_preview_context_empty_when_request_none(self):
        out = get_studio_preview_context("launch", None)
        self.assertEqual(out, {})

    def test_preview_context_normalizes_mode_case(self):
        request = Mock()
        request.school = None
        out = get_studio_preview_context("LAUNCH", request)
        self.assertEqual(out, {})
        out = get_studio_preview_context("  launch  ", request)
        self.assertEqual(out, {})

    @patch("apps.setup_studio.services.get_setup_studio_payload")
    def test_preview_context_launch_returns_impact_and_warnings_when_school_set(self, mock_payload):
        mock_payload.return_value = {
            "health_summary": {"tone": "ready", "label": "Launch ready", "detail": "Core blockers cleared."},
            "recommended_next": {"key": "launch", "label": "Launch", "link": "/studio/launch/"},
            "launch_blockers": [{"key": "plan_choice", "label": "Plan", "detail": "No plan attached."}],
            "launch_ready": False,
        }
        request = Mock()
        request.school = Mock()
        out = get_studio_preview_context("launch", request)
        self.assertIn("impact_summary", out)
        self.assertIn("1 blocker(s)", out["impact_summary"])
        self.assertEqual(len(out["dependency_warnings"]), 1)
        self.assertEqual(out["dependency_warnings"][0]["key"], "plan_choice")
        self.assertEqual(out["health_summary"]["label"], "Launch ready")
        self.assertEqual(out["recommended_next"]["key"], "launch")

    @patch("apps.setup_studio.services.get_setup_studio_payload")
    def test_preview_context_launch_ready_impact_summary(self, mock_payload):
        mock_payload.return_value = {"launch_blockers": [], "launch_ready": True}
        request = Mock()
        request.school = Mock()
        out = get_studio_preview_context("launch", request)
        self.assertIn("Launch ready", out.get("impact_summary", ""))

    def test_preview_url_returns_embed_url_for_modes(self):
        self.assertIn("embed=1", get_studio_preview_url("launch") or "")
        self.assertIn("embed=1", get_studio_preview_url("output") or "")
