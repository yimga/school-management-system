from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class WorldClassMarketingExperienceTests(SimpleTestCase):
    def test_homepage_has_product_visual_story_and_primary_cta(self):
        text = (ROOT / "templates" / "schools" / "marketing_landing.html").read_text(encoding="utf-8")
        self.assertIn("Run every campus from one offline-ready education operating system.", text)
        self.assertIn("data-world-class-marketing-story", text)
        self.assertIn("data-world-class-product-visual-map", text)
        for block in ("School Command Center", "Teacher Workspace", "Family Home", "Offline Sync", "Payment Readiness", "Blueprint Marketplace", "Trust / Audit"):
            self.assertIn(block, text)
        self.assertIn("marketing_demo", text)
        self.assertIn("marketing_resources_product_tour", text)

    def test_pricing_and_trust_keep_external_claims_honest(self):
        pricing = (ROOT / "templates" / "marketing" / "pricing_packages.html").read_text(encoding="utf-8")
        trust = (ROOT / "templates" / "marketing" / "pages" / "type_trust_center.html").read_text(encoding="utf-8")
        self.assertIn("data-world-class-billing-impact-preview", pricing)
        self.assertIn("external PSP readiness", pricing)
        self.assertIn("externally verified", trust)
        self.assertIn("data-mkt-trust-center", trust)
        forbidden = ("SOC 2 certified", "ISO certified", "PCI certified", "settlement proven")
        for phrase in forbidden:
            self.assertNotIn(phrase, pricing + trust)

    def test_marketing_links_are_not_dummy_actions(self):
        for rel in ("templates/schools/marketing_landing.html", "templates/marketing/pricing_packages.html", "templates/marketing/pages/type_trust_center.html"):
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertNotIn('href="#"', text)
                self.assertNotIn("javascript:void", text.lower())
