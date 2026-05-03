"""Experience Control closure slice — instrumentation + strict strip semantics."""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings


class MagicUxClosureSliceTests(SimpleTestCase):
    def _authenticated_request(self):
        rf = RequestFactory()
        req = rf.get("/portal/")
        from django.contrib.auth import get_user_model

        User = get_user_model()
        req.user = User(username="mux_closure", pk=1)
        return req

    def test_dashboard_empty_state_emits_click_measurement_hooks(self):
        html = render_to_string(
            "components/dashboard_empty_state.html",
            {
                "icon": "bi-inbox",
                "title": "Nothing yet",
                "message": "Desc",
                "action_url": "/a/",
                "action_text": "Go",
                "empty_primary_task": "demo_flow",
                "empty_primary_step": "demo:empty-primary",
                "secondary_action_url": "/help/",
                "secondary_action_text": "Help",
                "empty_secondary_step": "demo:empty-secondary",
            },
        )
        self.assertIn('data-action="empty-state-primary"', html)
        self.assertIn('data-task="demo_flow"', html)
        self.assertIn('data-task-step="demo:empty-primary"', html)
        self.assertIn('data-action="empty-state-secondary"', html)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_next_action_strict_fallback_chip_has_platform_task(self):
        req = self._authenticated_request()
        html = render_to_string(
            "components/next_action_strip.html",
            {
                "request": req,
                "rmc_system_actions_available": False,
                "rmc_system_actions": [],
                "rmc_conversion_single_action_enforced": True,
            },
        )
        self.assertIn('data-rmc-next-action-fallback="1"', html)
        self.assertIn('data-task="platform-next-action"', html)
        self.assertEqual(html.count('class="rmc-nas-chip"'), 1)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_next_action_strict_engine_slice_limits_chips(self):
        req = self._authenticated_request()
        html = render_to_string(
            "components/next_action_strip.html",
            {
                "request": req,
                "rmc_system_actions_available": True,
                "rmc_system_actions": [
                    {"title": "A", "action_url": "/a/", "type": "task", "source": "x"},
                    {"title": "B", "action_url": "/b/", "type": "task", "source": "x"},
                ],
                "rmc_conversion_single_action_enforced": True,
            },
        )
        self.assertEqual(html.count('class="rmc-nas-chip"'), 1)
        self.assertNotIn('rmc-nas-chip-title">B</span>', html)


class MagicUxStripAnonymousTests(SimpleTestCase):
    def test_strip_hidden_when_anonymous(self):
        rf = RequestFactory()
        req = rf.get("/")
        req.user = AnonymousUser()
        html = render_to_string(
            "components/next_action_strip.html",
            {"request": req},
        )
        self.assertEqual(html.strip(), "")
