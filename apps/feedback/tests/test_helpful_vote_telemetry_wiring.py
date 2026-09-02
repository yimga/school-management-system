from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_loads_static,
    assert_urls_reverse,
)

_TN_ROOT = Path(__file__).resolve().parents[3]


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
        # "feedback:contextual" is a {% url %} argument: present in the bytes of
        # a commented-out template. Reversing it proves the route EXISTS.
        assert_urls_reverse(self, _TN_ROOT / "templates/components/was_this_helpful.html")
        assert_loads_static(self, _TN_ROOT / "templates/components/was_this_helpful.html",
                            "js/_pages/components__was_this_helpful-1.js")
