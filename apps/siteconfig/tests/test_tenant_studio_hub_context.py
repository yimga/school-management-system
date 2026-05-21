"""School Studio hub context — productive coach copy."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.siteconfig.tenant_studio_hub_context import build_studio_coach_message


class TenantStudioHubContextTests(SimpleTestCase):
    def test_coach_message_names_next_action(self):
        msg, quick = build_studio_coach_message(
            progress={
                "percent": 20,
                "next_action": {
                    "label": "Academic year configured",
                    "url": "/siteconfig/onboarding/step/academic_year/",
                },
                "steps": [
                    {"label": "Students", "done": False, "link": "/students/"},
                ],
            },
            blockers=[],
        )
        self.assertIn("Academic year", msg)
        self.assertNotIn("Configure Ollama", msg)
        self.assertGreaterEqual(len(quick), 1)

    def test_coach_message_mentions_blocker_when_present(self):
        msg, _quick = build_studio_coach_message(
            progress={"percent": 10, "steps": []},
            blockers=["Activation checklist below 50%"],
        )
        self.assertIn("50%", msg)
