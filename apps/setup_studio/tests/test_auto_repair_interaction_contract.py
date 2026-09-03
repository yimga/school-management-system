from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup


ROOT = Path(__file__).resolve().parents[3]
_CTA_STRIP = ROOT / "templates/setup_studio/partials/zero_friction_cta_strip.html"


class AutoRepairInteractionContractTests(SimpleTestCase):
    def test_dialog_is_draggable_and_field_actions_are_direct(self):
        script = (ROOT / "static/js/rmc-setup-auto-repair.js").read_text(encoding="utf-8")
        self.assertIn('addEventListener("pointerdown"', script)
        self.assertIn("field.cta_url", script)
        self.assertIn("Fix the first issue", script)
        self.assertNotIn('>Continue</a>', script)
        # The drag handle is markup, and "draggable" is a claim about the dialog
        # on the page: a {% comment %} keeps the attribute in the bytes and gives
        # the pointerdown listener nothing to grab.
        assert_markup(self, _CTA_STRIP, "data-rmc-dialog-drag-handle")
