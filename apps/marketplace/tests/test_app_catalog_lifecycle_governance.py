from django.test import SimpleTestCase

from apps.platform_runtime.app_catalog_governance import (
    REVIEW_STATES,
    evaluate_app_publish_readiness,
)


class AppCatalogLifecycleGovernanceTests(SimpleTestCase):
    def test_publish_requires_review_security_privacy_docs_support_and_billing_truth(self):
        result = evaluate_app_publish_readiness(
            {
                "slug": "fee-collector",
                "review_state": "approved",
                "security_review": "approved",
                "privacy_review": "approved",
                "support_contact": "support@example.com",
                "docs_url": "https://docs.example.test/fee-collector",
                "scopes": ["finance:write"],
                "settlement_live": True,
            }
        )

        self.assertIn("submitted", REVIEW_STATES)
        self.assertFalse(result["ok"])
        self.assertEqual(result["external_readiness"], "external_required")
        self.assertIn("billing_truth", result["errors"])
