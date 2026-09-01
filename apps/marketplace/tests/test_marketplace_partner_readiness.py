from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup


ROOT = Path(__file__).resolve().parents[3]
_GOVERNANCE_CONSOLE = ROOT / "templates" / "marketplace" / "governance_console.html"


class MarketplacePartnerReadinessTests(SimpleTestCase):
    def test_marketplace_governance_explains_review_revenue_share_and_kill_switches(self):
        template = (
            ROOT / "templates" / "marketplace" / "governance_console.html"
        ).read_text(encoding="utf-8")
        # All four phrases live inside a single {% trans %} msgid, which is
        # template code: a parse cannot see it, and the console does not render
        # standalone because it extends control_plane_base. So these stay reads.
        self.assertIn("listing approvals", template)
        self.assertIn("security reviews", template)
        self.assertIn("kill switches", template)
        self.assertIn("revenue-share obligations", template)
        # What a read cannot tell is whether the guide is on the page at all.
        # id="gov-guide" is the section that holds all four, and it is emitted.
        assert_markup(self, _GOVERNANCE_CONSOLE, 'id="gov-guide"')

    def test_marketplace_partner_readiness_does_not_claim_live_settlement(self):
        template = (
            ROOT / "templates" / "marketplace" / "governance_console.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("settlement completed", template.lower())
        self.assertNotIn("live payout verified", template.lower())
