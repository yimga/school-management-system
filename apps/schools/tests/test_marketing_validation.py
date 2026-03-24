"""
Marketing URL resolution and smoke tests aligned with validate_marketing_urls and MARKETING_NON_NEGOTIABLES.
Ensures all key marketing routes resolve and return 200 on canonical host; landing renders required visual assets.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.schools.marketing_ai import get_marketing_ai_asset_url
from apps.schools.marketing_settings_helpers import derive_marketing_demo_tenant_url


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


class MarketingDemoTenantUrlDerivationTests(SimpleTestCase):
    """Pure helper: demo URL from slug + base when explicit env empty."""

    def test_explicit_url_wins_over_slug(self):
        self.assertEqual(
            derive_marketing_demo_tenant_url(
                "https://demo.example.com/",
                "foo",
                "runmycampus.com",
            ),
            "https://demo.example.com/",
        )

    def test_derives_from_slug_when_explicit_empty(self):
        self.assertEqual(
            derive_marketing_demo_tenant_url(
                "",
                "gilead-school",
                "runmycampus.com",
            ),
            "https://gilead-school.runmycampus.com/",
        )

    def test_empty_when_no_slug_or_base(self):
        self.assertEqual(derive_marketing_demo_tenant_url("", None, ""), "")
        self.assertEqual(
            derive_marketing_demo_tenant_url("", "myschool", ""),
            "",
        )


@override_settings(
    ALLOWED_HOSTS=["*"],
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    MARKETING_HERO_IMAGE_URL=None,
    MARKETING_HERO_VIDEO_URL=None,
    MARKETING_MIGRATION_FLOW_IMAGE_URL=None,
    MARKETING_SETUP_STUDIO_IMAGE_URL=None,
    MARKETING_ECOSYSTEM_IMAGE_URL=None,
    MARKETING_MARKETPLACE_IMAGE_URL=None,
)
class MarketingAiAssetFallbackTests(SimpleTestCase):
    """get_marketing_ai_asset_url returns static SVG paths when env overrides unset."""

    def test_static_fallbacks_for_image_keys(self):
        for key in (
            "hero_dashboard",
            "hero_migration_flow",
            "hero_setup_studio",
            "hero_ecosystem",
            "hero_marketplace",
        ):
            with self.subTest(key=key):
                url = get_marketing_ai_asset_url(key)
                self.assertTrue(url)
                self.assertIn(".svg", url)
                self.assertIn("/static/", url)

    def test_hero_video_no_forced_fallback(self):
        self.assertIsNone(get_marketing_ai_asset_url("hero_video"))


class MarketingContentJsonTests(SimpleTestCase):
    """Every file under config/marketing_content matches validate_marketing_urls shape."""

    def test_all_marketing_content_json_valid(self):
        mdir = Path(settings.BASE_DIR) / "config" / "marketing_content"
        self.assertTrue(mdir.is_dir(), str(mdir))
        required = ("label", "seo_title", "headline")
        for path in sorted(mdir.glob("*.json")):
            with self.subTest(file=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)
                for k in required:
                    self.assertTrue(
                        str(data.get(k, "") or "").strip(),
                        f"{path.name} needs non-empty {k}",
                    )
                segs = data.get("segments")
                if segs is not None:
                    self.assertIsInstance(segs, list)
                extras = data.get("extras")
                if extras is not None:
                    self.assertIsInstance(extras, dict)


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

    def test_smoke_json_backed_marketing_pages_return_200(self):
        """Pages with config/marketing_content/{slug}.json must still render."""
        for name in (
            "marketing_blog",
            "marketing_contact",
            "marketing_case_studies",
            "marketing_about",
        ):
            with self.subTest(url_name=name):
                path = reverse(name)
                resp = self.client.get(path, HTTP_HOST=self.host)
                self.assertEqual(resp.status_code, 200, f"GET {path} should return 200")


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingLandingContextTests(TestCase):
    """Landing must render required visual assets (NON_NEGOTIABLES 61–66) in HTML.

    Uses assertContains instead of response.context: under pytest the test client may
    not attach template context the same way as Django's DiscoverRunner in all setups.
    """

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

    def test_landing_renders_required_visual_assets(self):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        # Wired in _marketing_context / template fallbacks (static SVG paths in HTML)
        self.assertContains(resp, "images/marketing/migration-flow.svg")
        self.assertContains(resp, "images/marketing/platform-diagram-marketing.svg")
        self.assertContains(resp, "images/marketing/setup-studio-flow.svg")
        self.assertContains(resp, "images/marketing/viz-admin.svg")
        # Phase 10 narrative spine (verify_ux_completion.py markers)
        self.assertContains(resp, "data-phase10-marketing-narrative")
        self.assertContains(resp, "mkt-narrative-phase10")
        self.assertContains(resp, "Why schools switch")
        self.assertContains(resp, "Studio OS — one shell for every mode")


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
        self.assertContains(resp, "images/marketing/platform-diagram-marketing.svg")

    def test_products_analytics_page_returns_200_and_has_visual(self):
        resp = self.client.get("/products/analytics/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "images/marketing/platform-diagram-marketing.svg")

    def test_onboard_wizard_returns_200(self):
        resp = self.client.get("/onboard/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)


class MarketingJsonLoaderTests(SimpleTestCase):
    def test_compare_eu_json_loads_with_region(self):
        from apps.schools.marketing_views import _load_marketing_page_from_file

        loaded = _load_marketing_page_from_file("compare", region="eu")
        self.assertIsNotNone(loaded)
        page, _extras = loaded
        self.assertIn("GDPR", page.get("headline", ""))


@override_settings(
    ALLOWED_HOSTS=["*"],
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    MARKETING_CONTENT_REGION="eu",
)
class MarketingRegionalJsonIntegrationTests(TestCase):
    """MARKETING_CONTENT_REGION picks slug_region.json over slug.json."""

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

    def test_compare_page_prefers_region_json(self):
        resp = self.client.get("/compare/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "GDPR")


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingAbVariantTests(TestCase):
    """Session-sticky A/B: CTA order and hero B subline (see MARKETING_EXECUTION.md)."""

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
        # Hero A/B appends to hero_ai_line only when CMS did not set landing_hero_ai_line.
        try:
            from apps.siteconfig.models_marketing import MarketingContent

            MarketingContent.objects.filter(
                key__in=(
                    "landing_hero_ai_line",
                    "landing_hero_headline",
                    "landing_hero_subheadline",
                )
            ).delete()
        except Exception:
            pass

    def tearDown(self):
        self.env.stop()

    def test_secondary_cta_variant_puts_book_demo_first_in_hero(self):
        session = self.client.session
        session["marketing_cta_variant"] = "secondary"
        session.save()
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        hero_part = body.split('id="hero"', 1)[1].split('id="platform-pillars"', 1)[0]
        pos_demo = hero_part.find("Book a Demo")
        pos_trial = hero_part.find("Start Free Trial")
        self.assertGreater(pos_demo, -1, "hero should include Book a Demo")
        self.assertGreater(pos_trial, -1, "hero should include Start Free Trial")
        self.assertLess(
            pos_demo,
            pos_trial,
            "secondary variant should list Book a Demo before Start Free Trial in hero CTAs",
        )

    def test_hero_variant_b_appends_subline_when_no_cms(self):
        session = self.client.session
        session["marketing_ab_variant"] = "B"
        session.save()
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Operator-grade visibility")
        self.assertContains(resp, 'data-marketing-hero-variant="B"')
