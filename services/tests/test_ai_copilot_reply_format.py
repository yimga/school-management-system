"""Copilot rail reply formatting."""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai_copilot_reply_format import extract_copilot_rail_reply, format_guided_assistant_reply


class CopilotReplyFormatTests(SimpleTestCase):
    def test_format_guided_assistant_includes_summary_and_actions(self):
        text = format_guided_assistant_reply(
            {
                "summary": "Use Rapid Create on the manager host.",
                "actions": [{"title": "Open Rapid Create", "detail": "/super/schools/rapid/"}],
                "cautions": ["Verify slug availability before submit."],
            }
        )
        self.assertIn("Rapid Create", text)
        self.assertIn("Next steps", text)
        self.assertIn("Note:", text)

    def test_extract_prefers_guided_summary_over_empty_reply_key(self):
        reply = extract_copilot_rail_reply(
            {
                "summary": "Provision via the wizard.",
                "reply": "",
            }
        )
        self.assertIn("wizard", reply.lower())
