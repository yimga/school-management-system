"""SystemAction descriptions must never surface raw gateway context echoes."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.action_engine import _sanitize_system_action_description


class ActionEngineDescriptionSanitizeTests(SimpleTestCase):
    def test_strips_request_received_echo(self):
        raw = "Request received: {'status': 'setup_needed', 'score': 43}"
        self.assertEqual(_sanitize_system_action_description(raw), "")

    def test_strips_health_dict_repr(self):
        raw = str({"status": "setup_needed", "onboarding_percent": 82})
        self.assertEqual(_sanitize_system_action_description(raw), "")

    def test_keeps_human_copy(self):
        text = "Finish onboarding step 3 to unlock scheduled reports."
        self.assertEqual(_sanitize_system_action_description(text), text)
