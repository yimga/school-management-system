from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class DeveloperEcosystemReadinessTests(SimpleTestCase):
    def test_developer_templates_cover_onboarding_webhooks_review_and_sandbox(self):
        docs = (ROOT / "templates" / "apicenter" / "api_portal_docs.html").read_text(
            encoding="utf-8"
        )
        webhooks = (
            ROOT / "templates" / "apicenter" / "webhook_docs.html"
        ).read_text(encoding="utf-8")
        certification = (
            ROOT / "templates" / "apicenter" / "app_certification.html"
        ).read_text(encoding="utf-8")
        sandbox = (
            ROOT / "templates" / "apicenter" / "partner_sandbox.html"
        ).read_text(encoding="utf-8")

        self.assertIn("Developer onboarding guide", docs)
        self.assertIn("Publishing checklist", docs)
        self.assertIn("Webhook testing guide", webhooks)
        self.assertIn("App review policy", certification)
        self.assertIn("Partner sandbox guidance", sandbox)

    def test_developer_templates_do_not_fake_marketplace_or_payment_readiness(self):
        combined = "\n".join(
            [
                (ROOT / "templates" / "apicenter" / name).read_text(encoding="utf-8")
                for name in [
                    "api_portal_docs.html",
                    "webhook_docs.html",
                    "app_certification.html",
                    "partner_sandbox.html",
                ]
            ]
        )
        self.assertIn("external PSP proof", combined)
        self.assertNotIn("live payouts are enabled", combined.lower())
        self.assertNotIn("SOC2 certified", combined)
