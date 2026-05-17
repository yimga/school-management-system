"""Phase 1 marketing foundation regression tests."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.schools.tests.test_marketing_phase0_visual_truth import assert_no_exact_plan_pound_teasers


REPO_ROOT = Path(__file__).resolve().parents[3]
LANDING = REPO_ROOT / "templates" / "schools" / "marketing_landing_v2.html"
BASE_MARKETING = REPO_ROOT / "templates" / "marketing" / "base_marketing.html"


class MarketingPhase1AssetsTest(SimpleTestCase):
    def test_schoolhouse_and_v3_css_exist(self) -> None:
        for rel in (
            "static/marketing/css/tokens-schoolhouse.css",
            "static/marketing/css/marketing-v3-shell.css",
            "static/marketing/css/marketing-v3-narrative.css",
            "static/marketing/css/marketing-v3-dashboards.css",
        ):
            self.assertTrue((REPO_ROOT / rel).is_file(), rel)

    def test_v3_js_exists(self) -> None:
        for rel in (
            "static/marketing/js/theme-toggle.js",
            "static/marketing/js/scroll-narrative.js",
            "static/marketing/js/rotating-headline.js",
        ):
            self.assertTrue((REPO_ROOT / rel).is_file(), rel)

    def test_core_partials_exist(self) -> None:
        for rel in (
            "templates/marketing/components/_bell_clock_sticky.html",
            "templates/marketing/components/_persona_tabs.html",
            "templates/marketing/components/_dashboard_frame.html",
            "templates/marketing/components/_rotating_headline.html",
            "templates/marketing/components/_theme_toggle.html",
            "templates/marketing/components/_product_proof_block.html",
        ):
            self.assertTrue((REPO_ROOT / rel).is_file(), rel)


class MarketingPhase1HomeWiringTest(SimpleTestCase):
    def test_home_includes_bell_clock_and_persona_tabs(self) -> None:
        text = LANDING.read_text(encoding="utf-8")
        self.assertIn("_bell_clock_sticky.html", text)
        self.assertIn("_persona_tabs.html", text)
        self.assertIn("_rotating_headline.html", text)
        self.assertIn("_dashboard_frame.html", text)
        self.assertIn("_product_proof_block.html", text)
        self.assertIn("mkt-edt-voices--compact", text)
        assert_no_exact_plan_pound_teasers(self, text)

    def test_base_marketing_loads_v3_assets(self) -> None:
        text = BASE_MARKETING.read_text(encoding="utf-8")
        self.assertIn("tokens-schoolhouse.css", text)
        self.assertIn("scroll-narrative.js", text)
        self.assertIn("theme-toggle.js", text)
        self.assertIn('data-theme="light"', text)
