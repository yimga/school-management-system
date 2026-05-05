from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class MarketplacePartnerReadinessTests(SimpleTestCase):
    def test_marketplace_governance_explains_review_revenue_share_and_kill_switches(self):
        template = (
            ROOT / "templates" / "marketplace" / "governance_console.html"
        ).read_text(encoding="utf-8")
        self.assertIn("listing approvals", template)
        self.assertIn("security reviews", template)
        self.assertIn("kill switches", template)
        self.assertIn("revenue-share obligations", template)

    def test_marketplace_partner_readiness_does_not_claim_live_settlement(self):
        template = (
            ROOT / "templates" / "marketplace" / "governance_console.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("settlement completed", template.lower())
        self.assertNotIn("live payout verified", template.lower())
