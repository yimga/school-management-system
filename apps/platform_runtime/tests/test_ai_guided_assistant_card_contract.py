"""AI guided assistant card — dark-surface contract (no Bootstrap white leak)."""

from pathlib import Path

from django.test import SimpleTestCase


class AiGuidedAssistantCardContractTests(SimpleTestCase):
    def test_partial_uses_semantic_component_not_bootstrap_card(self):
        text = Path("templates/components/ai_guided_assistant_card.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-ai-guided-assistant-card", text)
        self.assertIn("data-rmc-ai-guided-assistant-card", text)
        self.assertNotIn('class="card ', text)
        self.assertNotIn("text-muted", text)
        self.assertNotIn("text-primary small", text)

    def test_stylesheet_avoids_hardcoded_white_background(self):
        css = Path("static/css/rmc-ai-guided-assistant-card.css").read_text(
            encoding="utf-8"
        )
        self.assertNotRegex(css, r"background\s*:\s*#fff(?:fff)?\b", msg=css)
        self.assertNotRegex(css, r"background\s*:\s*white\b", msg=css)
        self.assertIn("--surface-elevated", css)
        self.assertIn(".rmc-ai-guided-assistant-card__cta", css)

    def test_control_plane_shell_links_assistant_stylesheet(self):
        skeleton = Path("templates/control_plane_skeleton.html").read_text(
            encoding="utf-8"
        )
        base = Path("templates/control_plane_base.html").read_text(encoding="utf-8")
        self.assertIn("rmc-ai-guided-assistant-card.css", skeleton)
        self.assertIn("rmc-ai-guided-assistant-card.css", base)

    def test_dark_mode_cta_uses_high_contrast_token(self):
        css = Path("static/css/rmc-ai-guided-assistant-card.css").read_text(
            encoding="utf-8"
        )
        self.assertIn('html[data-surface="control-plane"]', css)
        self.assertIn("rmc-ai-guided-assistant-card__cta", css)
