from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup


ROOT = Path(__file__).resolve().parents[3]
PRICING_PACKAGES = ROOT / "templates" / "marketing" / "pricing_packages.html"


class PackageBillingWorldClassUXTests(SimpleTestCase):
    def test_platform_billing_has_package_usage_psp_and_manual_fallback_context(self):
        text = (ROOT / "templates" / "schools" / "billing_dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Package and Billing Command Center", text)
        self.assertIn("Package comparison", text)
        self.assertIn("entitlement diff", text)
        self.assertIn("usage meters", text)
        self.assertIn("billing impact", text)
        self.assertIn("external PSP status", text)
        self.assertIn("manual fallback", text)

    def test_money_center_has_payment_readiness_and_no_fake_psp_claim(self):
        text = (ROOT / "templates" / "finance" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Money Center", text)
        self.assertIn("Payment readiness", text)
        self.assertIn("live PSP collection requires external onboarding", text)
        self.assertIn("No fake live payments", text)

    def test_pricing_packages_show_billing_impact_preview(self):
        text = PRICING_PACKAGES.read_text(encoding="utf-8")
        # The preview hook is markup a buyer either sees or does not; the honesty
        # sentence sits inside {% trans %}, which a parse cannot see and this page
        # cannot render standalone, so that one stays a read.
        assert_markup(self, PRICING_PACKAGES, "data-world-class-billing-impact-preview")
        self.assertIn("data-world-class-billing-impact-preview", text)
        self.assertIn("Final billing requires contract", text)
