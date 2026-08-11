from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class GuidedActionSurfaceContractTests(SimpleTestCase):
    def test_ai_guided_action_styles_are_owned_by_authenticated_shells(self):
        stylesheet = "css/rmc-ai-guided-assistant-card.css"
        for relative in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(stylesheet, source, relative)

    def test_open_in_ai_center_is_a_visible_pill_action(self):
        component = (ROOT / "templates/components/ai_guided_assistant_card.html").read_text(
            encoding="utf-8"
        )
        css = (ROOT / "static/css/rmc-ai-guided-assistant-card.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-ai-guided-assistant-card__cta", component)
        self.assertIn("border-radius: 999px", css)
        self.assertIn("text-decoration: none", css)

    def test_preview_and_apply_actions_use_action_classes(self):
        for relative in (
            "templates/marketplace/templates_preview_frame.html",
            "templates/marketplace/templates_apply_confirm.html",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("rmc-template-", source)
            self.assertNotIn("<a href=", source, relative)

    def test_api_center_instruction_is_not_rendered_as_plain_text(self):
        source = (
            ROOT / "templates/apicenter/partials/dashboard_body.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Manage config & scopes", source)
        self.assertIn("btn-outline-primary", source)
        self.assertNotIn("btn btn-link btn-sm p-0", source)
