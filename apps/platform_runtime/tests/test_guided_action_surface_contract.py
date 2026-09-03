from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup


ROOT = Path(__file__).resolve().parents[3]

GUIDED_CARD = ROOT / "templates/components/ai_guided_assistant_card.html"
APICENTER_BODY = ROOT / "templates/apicenter/partials/dashboard_body.html"


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
        css = (ROOT / "static/css/rmc-ai-guided-assistant-card.css").read_text(
            encoding="utf-8"
        )
        # The pill is only visible if the card EMITS the CTA element. Reading the
        # template's bytes could not tell that from a CTA inside {% comment %},
        # so the engine answers this half; the CSS half stays a file read.
        assert_markup(self, GUIDED_CARD, "rmc-ai-guided-assistant-card__cta")
        self.assertIn("border-radius: 999px", css)
        self.assertIn("text-decoration: none", css)

    def test_preview_and_apply_actions_use_action_classes(self):
        for relative in (
            "templates/marketplace/templates_preview_frame.html",
            "templates/marketplace/templates_apply_confirm.html",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            # assertNotIn is an absence over bytes, so the read stays. The
            # action classes are markup, so they are ALSO asked of the engine --
            # keeping the assertIn is what keeps this case scored by the gate.
            self.assertIn("rmc-template-", source)
            assert_markup(self, ROOT / relative, "rmc-template-")
            self.assertNotIn("<a href=", source, relative)

    def test_api_center_instruction_is_not_rendered_as_plain_text(self):
        source = (
            ROOT / "templates/apicenter/partials/dashboard_body.html"
        ).read_text(encoding="utf-8")
        # "Manage config & scopes" is inside {% trans %} -- template code, which
        # no parse sees and which this partial does not reach on a bare render --
        # and the last line is an absence. Both stay reads. The button class is
        # markup, and "not rendered as plain text" is precisely a claim about
        # what gets emitted, so that one goes through the engine.
        self.assertIn("Manage config & scopes", source)
        self.assertIn("btn-outline-primary", source)
        assert_markup(self, APICENTER_BODY, "btn-outline-primary")
        self.assertNotIn("btn btn-link btn-sm p-0", source)
