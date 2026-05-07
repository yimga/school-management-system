from django.test import SimpleTestCase

from apps.platform_runtime.app_catalog_governance import evaluate_app_publish_readiness


class AppPublishingChecklistTests(SimpleTestCase):
    def test_complete_checklist_can_publish_with_live_settlement_only_when_proven(self):
        result = evaluate_app_publish_readiness(
            {
                "slug": "gradebook-export",
                "review_state": "approved",
                "security_review": "approved",
                "privacy_review": "approved",
                "support_contact": "dev@example.com",
                "docs_url": "https://docs.example.test/gradebook-export",
                "scopes": ["reports:read"],
                "settlement_live": True,
                "settlement_proof": "docs/generated/provider-proof.json",
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["external_readiness"], "live_verified")
