from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]
COMPONENTS = ROOT / "templates" / "components"


class WorldClassComponentContractTests(SimpleTestCase):
    def test_components_render_required_markers(self):
        required = {
            "world_class_page_hero.html": "data-world-class-page-hero",
            "world_class_summary_strip.html": "data-world-class-summary-strip",
            "world_class_product_moment_card.html": "data-world-class-product-moment",
            "world_class_action_rail.html": "data-world-class-action-rail",
            "world_class_empty_state.html": "data-world-class-empty-state",
            "world_class_risk_blocker_card.html": "data-world-class-risk-blocker",
            "world_class_guided_stepper.html": "data-world-class-guided-stepper",
            "world_class_readiness_meter.html": "data-world-class-readiness-meter",
            "world_class_timeline.html": "data-world-class-timeline",
            "world_class_visual_section_header.html": "data-world-class-section-header",
        }
        for name, marker in required.items():
            with self.subTest(name=name):
                text = (COMPONENTS / name).read_text(encoding="utf-8")
                self.assertIn(marker, text)
                get_template(f"components/{name}")

    def test_primary_action_slots_and_empty_state_have_actions(self):
        hero = (COMPONENTS / "world_class_page_hero.html").read_text(encoding="utf-8")
        empty = (COMPONENTS / "world_class_empty_state.html").read_text(encoding="utf-8")
        action_rail = (COMPONENTS / "world_class_action_rail.html").read_text(encoding="utf-8")
        self.assertIn("data-world-class-primary-action-slot", hero)
        self.assertIn("data-world-class-primary-action-slot", empty)
        self.assertIn("data-world-class-primary-action-slot", action_rail)
        self.assertIn("primary_url", empty)
        self.assertIn("secondary_url", empty)

    def test_no_dummy_href_or_action_in_world_class_components(self):
        for path in COMPONENTS.glob("world_class_*.html"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn('href="#"', text)
                self.assertNotIn("javascript:void", text.lower())
                self.assertNotIn("todo", text.lower())

    def test_focus_aria_and_mobile_css_basics(self):
        css = (ROOT / "static" / "css" / "rmc-world-class-experience.css").read_text(encoding="utf-8")
        hero = (COMPONENTS / "world_class_page_hero.html").read_text(encoding="utf-8")
        stepper = (COMPONENTS / "world_class_guided_stepper.html").read_text(encoding="utf-8")
        meter = (COMPONENTS / "world_class_readiness_meter.html").read_text(encoding="utf-8")
        self.assertIn("aria-labelledby", hero)
        self.assertIn("aria-label", stepper)
        self.assertIn('role="meter"', meter)
        self.assertIn("@media (max-width: 991.98px)", css)
        self.assertIn("prefers-reduced-motion", css)
