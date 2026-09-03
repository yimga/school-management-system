"""AI guided assistant card — dark-surface contract (no Bootstrap white leak)."""

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_loads_static,
    assert_markup,
    assert_wires,
)


class AiGuidedAssistantCardContractTests(SimpleTestCase):
    def test_partial_uses_semantic_component_not_bootstrap_card(self):
        path = Path("templates/components/ai_guided_assistant_card.html")
        text = path.read_text(encoding="utf-8")
        # The three negatives are the point of this contract (no Bootstrap white
        # leak) and the mutation deliberately does not feed an assertNotIn, so
        # they stay reads over the source.
        self.assertNotIn('class="card ', text)
        self.assertNotIn("text-muted", text)
        self.assertNotIn("text-primary small", text)
        # Both positives are markup, and a read of them passes over a partial whose
        # whole body sits inside {% comment %} -- a card that is not on the page at
        # all, which satisfies "not a Bootstrap card" for the wrong reason.
        assert_markup(
            self,
            path,
            "rmc-ai-guided-assistant-card",
            "data-rmc-ai-guided-assistant-card",
        )

    def test_stylesheet_avoids_hardcoded_white_background(self):
        css = Path("static/css/rmc-ai-guided-assistant-card.css").read_text(
            encoding="utf-8"
        )
        self.assertNotRegex(css, r"background\s*:\s*#fff(?:fff)?\b", msg=css)
        self.assertNotRegex(css, r"background\s*:\s*white\b", msg=css)
        self.assertIn("--surface-elevated", css)
        self.assertIn(".rmc-ai-guided-assistant-card__cta", css)

    def test_control_plane_shell_links_assistant_stylesheet(self):
        # This asked control_plane_base.html for its own <link> and went red:
        # base EXTENDS the skeleton, so a copy there would be a duplicate tag.
        # The contract is that every control-plane page gets the sheet, which
        # is the skeleton's job plus the inheritance. Both halves, through the
        # engine, so a commented-out shell fails.
        assert_loads_static(
            self,
            "templates/control_plane_skeleton.html",
            "rmc-ai-guided-assistant-card.css",
        )
        assert_wires(
            self,
            "templates/control_plane_base.html",
            "control_plane_skeleton.html",
        )

    def test_dark_mode_cta_uses_high_contrast_token(self):
        css = Path("static/css/rmc-ai-guided-assistant-card.css").read_text(
            encoding="utf-8"
        )
        self.assertIn('html[data-surface="control-plane"]', css)
        self.assertIn("rmc-ai-guided-assistant-card__cta", css)
