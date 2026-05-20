"""Marketing sovereign KB search (batch 1357)."""

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.portal.marketing_kb import marketing_kb_queryset, marketing_kb_tenant_slug


class MarketingKbSlugTests(SimpleTestCase):
    @override_settings(
        MARKETING_KB_TENANT_SLUG="custom-corpus",
        TENANT_EXAMPLE_SLUG="demo-school",
    )
    def test_slug_prefers_explicit_setting(self):
        self.assertEqual(marketing_kb_tenant_slug(), "custom-corpus")


class MarketingKbUrlTests(TestCase):
    def test_search_route_resolves(self):
        self.assertEqual(
            reverse("marketing_kb_search"),
            "/resources/help-center/search/",
        )

    def test_typeahead_route_resolves(self):
        self.assertEqual(
            reverse("marketing_kb_typeahead"),
            "/api/v1/marketing/kb/typeahead/",
        )

    def test_category_route_resolves(self):
        self.assertEqual(
            reverse("marketing_kb_category", kwargs={"category_slug": "billing"}),
            "/resources/help-center/category/billing/",
        )

    def test_search_page_renders(self):
        resp = self.client.get(reverse("marketing_kb_search"), {"q": "billing"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Knowledge base search")

    def test_typeahead_json(self):
        resp = self.client.get(
            reverse("marketing_kb_typeahead"),
            {"q": "help"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("suggestions", data)

    def test_support_hub_redirects_query(self):
        resp = self.client.get(reverse("public_support_hub"), {"q": "enrollment"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/resources/help-center/search/", resp["Location"])
        self.assertIn("q=enrollment", resp["Location"])


class MarketingKbQuerysetTests(SimpleTestCase):
    def test_queryset_filters_global_published(self):
        qs = marketing_kb_queryset()
        self.assertIn("is_global_article", str(qs.query))
