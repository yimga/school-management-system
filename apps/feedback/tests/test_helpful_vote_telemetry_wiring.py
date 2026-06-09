from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class HelpfulVoteTelemetryWiringTests(SimpleTestCase):
    def test_component_posts_to_contextual_feedback(self):
        template = (ROOT / "templates/components/was_this_helpful.html").read_text(
            encoding="utf-8"
        )
        script = (
            ROOT / "static/js/_pages/components__was_this_helpful-1.js"
        ).read_text(encoding="utf-8")
        self.assertIn("feedback:contextual", template)
        self.assertIn("persistVote", script)
        self.assertIn("X-Requested-With", script)
        self.assertNotIn("{% trans", script)
