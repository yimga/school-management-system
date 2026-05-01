"""Magic UX surface markers: fragments without full portal shell + CCC strip."""

from __future__ import annotations

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class DashboardEmptyStateMagicUxTests(SimpleTestCase):
    def test_renders_primary_and_secondary_actions(self):
        html = render_to_string(
            "components/dashboard_empty_state.html",
            {
                "icon": "bi-inbox",
                "title": "Nothing yet",
                "message": "Try the export.",
                "action_url": "/a/",
                "action_text": "Go",
                "secondary_action_url": "/b/",
                "secondary_action_text": "Alt",
            },
        )
        self.assertIn("dashboard-empty-state", html)
        self.assertIn('data-empty-state="action-state"', html)


class CccGuidedActivationStripMagicUxTests(SimpleTestCase):
    def test_next_action_link_has_measurement_attrs(self):
        html = render_to_string(
            "siteconfig/partials/ccc_guided_activation_strip.html",
            {
                "ccc_onboarding": {
                    "total": 4,
                    "completed": 1,
                    "percent": 25,
                    "next_action": {"url": "/next/", "label": "Finish setup"},
                    "display_steps": [
                        {"done": False, "label": "Step A", "link": "/a/"},
                    ],
                }
            },
        )
        self.assertIn('data-task="ccc_activation"', html)
        self.assertIn("ccc:guided-next", html)
