from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_urls_reverse,
    assert_wires,
)

_TN_ROOT = Path(__file__).resolve().parents[3]


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
        # Every needle above is a {% trans %} msgid, invisible to a parse.
        # The docs page really extending the backend shell is not.
        assert_wires(self, _TN_ROOT / "templates/apicenter/api_portal_docs.html",
                     "backend_base.html")
        assert_urls_reverse(self, _TN_ROOT / "templates/apicenter/api_portal_docs.html")

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
