from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class AutoRepairInteractionContractTests(SimpleTestCase):
    def test_dialog_is_draggable_and_field_actions_are_direct(self):
        template = (ROOT / "templates/setup_studio/partials/zero_friction_cta_strip.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/rmc-setup-auto-repair.js").read_text(encoding="utf-8")
        self.assertIn("data-rmc-dialog-drag-handle", template)
        self.assertIn('addEventListener("pointerdown"', script)
        self.assertIn("field.cta_url", script)
        self.assertIn("Fix the first issue", script)
        self.assertNotIn('>Continue</a>', script)
