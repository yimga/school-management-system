"""
Marketing URL resolution and smoke tests aligned with validate_marketing_urls and MARKETING_NON_NEGOTIABLES.
Ensures all key marketing routes resolve and return 200 on canonical host; landing context has required visual keys.
"""
import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse


# URL names exercised by manage.py validate_marketing_urls (and --smoke subset)
MARKETING_URL_NAMES = [
    "marketing_landing",
    "marketing_book_demo",
    "marketing_10_reasons",
    "marketing_interactive_preview",
    "marketing_integrations",
    "marketing_app_marketplace",
    "marketing_developers",
    "marketing_products_admissions",
    "marketing_products_analytics",
    "marketing_funnel_dashboard",
    "marketing_robots_txt",
    "marketing_sitemap_xml",
    "signup_school",
    "global_login_discovery",
]
SMOKE_URL_NAMES = [
    "marketing_landing",
    "marketing_book_demo",
    "marketing_10_reasons",
    "marketing_integrations",
    "marketing_app_marketplace",
    "marketing_developers",
]

# Required context keys for landing (Visual Asset / NON_NEGOTIABLES 61-66)
LANDING_VISUAL_CONTEXT_KEYS = [
    "migration_studio_image_url",
    "platform_architecture_diagram_url",
    "school_in_a_box_flow_image_url",
    "data_intelligence_loop_image_url",
    "product_visualization_slides",
]


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingUrlResolutionTests(TestCase):
    """All marketing URL names must resolve (same as validate_marketing_urls)."""

    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_all_marketing_url_names_resolve(self):
        for name in MARKETING_URL_NAMES:
            with self.subTest(url_name=name):
                path = reverse(name)
                self.assertTrue(path, f"{name} should resolve to a non-empty path")


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingSmokeTests(TestCase):
    """Key marketing URLs must return 200 on canonical host (same as validate_marketing_urls --smoke)."""

    def setUp(self):
        self.client = Client()
        self.host = "runmycampus.com"
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_smoke_marketing_landing_returns_200(self):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "RunMyCampus")

    def test_smoke_key_marketing_urls_return_200(self):
        for name in SMOKE_URL_NAMES:
            with self.subTest(url_name=name):
                path = reverse(name)
                resp = self.client.get(path, HTTP_HOST=self.host)
                self.assertEqual(resp.status_code, 200, f"GET {path} should return 200")


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingLandingContextTests(TestCase):
    """Landing view must provide required visual context keys (NON_NEGOTIABLES 61-66)."""

    def setUp(self):
        self.client = Client()
        self.host = "runmycampus.com"
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_landing_context_contains_required_visual_keys(self):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        for key in LANDING_VISUAL_CONTEXT_KEYS:
            with self.subTest(context_key=key):
                self.assertIn(key, resp.context, f"Landing context must include '{key}'")
        self.assertTrue(
            resp.context.get("migration_studio_image_url"),
            "migration_studio_image_url must be non-empty (fallback in view)",
        )
        self.assertTrue(
            resp.context.get("platform_architecture_diagram_url"),
            "platform_architecture_diagram_url must be non-empty",
        )
        self.assertTrue(
            isinstance(resp.context.get("product_visualization_slides"), list),
            "product_visualization_slides must be a list",
        )


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingPageExtrasTests(TestCase):
    """Key marketing subpages must render with page_extras (diagram or data_viz where expected)."""

    def setUp(self):
        self.client = Client()
        self.host = "runmycampus.com"
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_platform_page_returns_200(self):
        resp = self.client.get("/platform/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("page_extras", resp.context)

    def test_products_analytics_page_returns_200_and_has_visual(self):
        resp = self.client.get("/products/analytics/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("page_extras", resp.context)
        extras = resp.context["page_extras"]
        self.assertIn("data_viz_path", extras, "products-analytics must have data_viz_path")
        self.assertTrue(extras.get("data_viz_path"), "data_viz_path must be set")

    def test_onboard_wizard_returns_200(self):
        resp = self.client.get("/onboard/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
