"""Marketing region affordance — local-first · global-next helpers."""

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.schools.marketing_region import (
    build_marketing_region_affordance,
    institution_regional_callout,
    regional_landing_path,
    trust_regulatory_cards_for_country,
)


class MarketingRegionHelperTests(SimpleTestCase):
    def test_regional_landing_path_canonical(self):
        self.assertEqual(regional_landing_path("NG", "en"), "/en/ng/")
        self.assertEqual(regional_landing_path("CM", "fr"), "/fr/cm/")

    def test_affordance_when_country_detected(self):
        ctx = build_marketing_region_affordance(
            country_code="NG",
            country_label="Nigeria",
            language_code="en",
        )
        self.assertTrue(ctx["marketing_region_show_affordance"])
        self.assertEqual(ctx["marketing_region_landing_path"], "/en/ng/")

    def test_trust_regulatory_prioritizes_country_framework(self):
        base = [
            {
                "id": "ferpa",
                "title": "FERPA",
                "summary": "x",
                "url_name": "marketing_trust_ferpa",
                "deep_dive_label": "FERPA",
            },
            {
                "id": "gdpr",
                "title": "GDPR",
                "summary": "x",
                "url_name": "marketing_trust_gdpr",
                "deep_dive_label": "GDPR",
            },
        ]
        cards = trust_regulatory_cards_for_country(base, "ZA")
        titles = [c["title"] for c in cards]
        self.assertIn("POPIA", titles)
        self.assertTrue(cards[0].get("highlight"))

    def test_institution_callout_international_ng(self):
        row = institution_regional_callout(
            "international-schools",
            country_code="NG",
            country_label="Nigeria",
        )
        self.assertIsNotNone(row)
        self.assertIn("Nigeria", row["eyebrow"])


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    MARKETING_GEO_COUNTRY_OVERRIDE="NG",
)
class MarketingRegionHttpTests(TestCase):
    def test_trust_center_renders_region_affordance_marker(self):
        client = Client()
        resp = client.get(
            reverse("marketing_trust_center"),
            HTTP_HOST="runmycampus.com",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-mkt-local-first-global-next", body)
        self.assertNotIn("North Star", body)

    def test_canonical_regional_route_resolves(self):
        client = Client()
        resp = client.get("/en/ng/", HTTP_HOST="runmycampus.com")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"data-mkt-region-affordance", resp.content)
