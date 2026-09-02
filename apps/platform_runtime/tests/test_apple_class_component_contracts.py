from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_markup,
)

_TN_ROOT = Path(__file__).resolve().parents[3]


ROOT = Path(__file__).resolve().parents[3]
COMPONENTS = ROOT / "templates" / "components"


class AppleClassComponentContractTests(SimpleTestCase):
    def test_apple_class_components_render_required_markers(self):
        required = {
            "apple_class_glass_panel.html": "data-apple-class-glass-panel",
            "apple_class_status_pill.html": "data-apple-class-status-pill",
            "apple_class_metric_card.html": "data-apple-class-metric-card",
            "apple_class_quick_profile_drawer.html": "data-apple-class-quick-profile-drawer",
            "apple_class_inline_edit_field.html": "data-apple-class-inline-edit-field",
            "apple_class_visual_workflow_path.html": "data-apple-class-visual-workflow-path",
            "apple_class_dependency_graph.html": "data-apple-class-dependency-graph",
            "apple_class_data_quality_meter.html": "data-apple-class-data-quality-meter",
        }
        for name, marker in required.items():
            with self.subTest(name=name):
                text = (COMPONENTS / name).read_text(encoding="utf-8")
                self.assertIn(marker, text)
                get_template(f"components/{name}")

    def test_direct_manipulation_and_accessibility_contracts(self):
        drawer = (COMPONENTS / "apple_class_quick_profile_drawer.html").read_text(encoding="utf-8")
        inline = (COMPONENTS / "apple_class_inline_edit_field.html").read_text(encoding="utf-8")
        meter = (COMPONENTS / "apple_class_data_quality_meter.html").read_text(encoding="utf-8")
        self.assertIn("aria-expanded", drawer)
        self.assertIn("tabindex", drawer)
        self.assertIn("data-apple-class-primary-action-slot", drawer)
        self.assertIn("<label", inline)
        self.assertIn("aria-label", inline)
        self.assertIn('role="meter"', meter)
        # An accessible name only reaches a screen reader if it is EMITTED.
        assert_markup(self, _TN_ROOT / "templates/components/apple_class_data_quality_meter.html",
                      'role="meter"', "rmc-acx-data-quality")

    def test_css_supports_depth_mobile_and_reduced_motion(self):
        css = (ROOT / "static" / "css" / "rmc-world-class-experience.css").read_text(encoding="utf-8")
        for token in (
            "--rmc-acx-glass",
            "backdrop-filter",
            ".rmc-acx-drawer",
            ".rmc-acx-workflow-path",
            ".rmc-acx-dependency-graph",
            "@media (max-width: 991.98px)",
            "prefers-reduced-motion",
        ):
            with self.subTest(token=token):
                self.assertIn(token, css)

    def test_no_dummy_href_or_action_in_apple_class_components(self):
        for path in COMPONENTS.glob("apple_class_*.html"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8").lower()
                self.assertNotIn('href="#"', text)
                self.assertNotIn("javascript:void", text)
                self.assertNotIn("todo", text)
