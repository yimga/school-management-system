from django.test import SimpleTestCase

from apps.platform_runtime.package_rollout import billing_impact_preview


class PackageBillingImpactPreviewTests(SimpleTestCase):
    def test_billing_preview_never_allows_charge_without_psp_proof(self):
        impact = billing_impact_preview(
            {"price": "100"},
            {"price": "200", "psp_live_verified": True},
        )

        self.assertEqual(impact["projected_price"], "200")
        self.assertEqual(impact["external_psp_state"], "external_required")
        self.assertTrue(impact["manual_fallback"])
        self.assertFalse(impact["charge_permitted"])
