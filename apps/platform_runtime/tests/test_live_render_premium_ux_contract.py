from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class LiveRenderPremiumUXContractTests(SimpleTestCase):
    def test_live_audit_artifact_can_be_recorded_without_credentials(self):
        audit_dir = ROOT / "test-results" / "live-render-premium-audit"
        if not audit_dir.exists():
            self.skipTest("live Render audit artifacts are generated during browser QA")

        audit = audit_dir / "audit.json"
        self.assertTrue(audit.exists())
        body = audit.read_text(encoding="utf-8", errors="replace").lower()
        self.assertIn("manager.runmycampus.com", body)
        self.assertNotIn('"password"', body)
        self.assertNotIn("admin admin", body)

    def test_premium_standard_document_exists(self):
        standard = ROOT / "docs" / "design" / "RUNMYCAMPUS_PREMIUM_UX_STANDARD.md"
        body = standard.read_text(encoding="utf-8")
        self.assertIn("One primary action per screen", body)
        self.assertIn("No fake payment or PSP readiness", body)
        self.assertIn("data-rmc-premium-shell", body)
