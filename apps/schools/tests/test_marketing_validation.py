"""
Marketing URL resolution and smoke tests aligned with validate_marketing_urls and MARKETING_NON_NEGOTIABLES.
Ensures all key marketing routes resolve and return 200 on canonical host; landing renders required visual assets.
"""

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

from django.conf import settings
from django.test.client import ContextList
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.core.management import call_command
from django.urls import reverse

from apps.schools.marketing_ai import get_marketing_ai_asset_url
from apps.schools.marketing_url_inventory import (
    iter_marketing_adjacent_smoke_targets,
    iter_marketing_smoke_targets,
)
from apps.schools.marketing_settings_helpers import derive_marketing_demo_tenant_url


def _store_rendered_templates_without_context_copy(store, signal, sender, template, context, **kwargs):
    store.setdefault("templates", []).append(template)
    if "context" not in store:
        store["context"] = ContextList()
    store["context"].append(context)


# URL names exercised by manage.py validate_marketing_urls (and --smoke subset)
MARKETING_URL_NAMES = [
    "marketing_landing",
    "marketing_demo",
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
    "marketing_trust_dedicated",
    "marketing_pricing_packages_clarity",
    "marketing_story_implementation",
    "marketing_story_offline_first",
    "marketing_story_payments_readiness",
    "marketing_story_private_schools",
    "marketing_story_school_networks",
    "marketing_story_pilot_program",
    "marketing_procurement_checklist",
    "marketing_implementation_assurance",
    "marketing_security_packet_request",
    "marketing_security_packet_submit",
]
SMOKE_URL_NAMES = [
    "marketing_landing",
    "marketing_demo",
    "marketing_book_demo",
    "marketing_10_reasons",
    "marketing_integrations",
    "marketing_app_marketplace",
    "marketing_developers",
    "marketing_trust_dedicated",
    "marketing_pricing_packages_clarity",
    "marketing_procurement_checklist",
    "marketing_implementation_assurance",
    "marketing_security_packet_request",
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
                "demo-tenant",
                "runmycampus.com",
            ),
            "https://demo-tenant.runmycampus.com/",
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
                resp = self.client.get(path, HTTP_HOST=self.host, follow=True)
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
                resp = self.client.get(path, HTTP_HOST=self.host, follow=True)
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
        # Homepage now renders the editorial v2 visual system with inline SVG artifacts.
        self.assertContains(resp, "marketing/css/marketing-landing-v2.css")
        self.assertContains(resp, "mkt-edt-hero__artifact")
        self.assertContains(resp, "mkt-edt-crests__strip")
        self.assertContains(resp, "mkt-edt-frieze")
        self.assertContains(resp, "mkt-edt-job__artifact")
        self.assertContains(resp, "mkt-edt-lens__panel")
        self.assertContains(resp, "mkt-edt-walkthrough__reel")

    def test_landing_renders_admissions_flow_post_enrollment_and_what_you_get(self):
        """MARKETING_PAGE_AUDIT: context keys must surface on HTML (was context-only)."""
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Run your school the way your school actually runs.")
        self.assertContains(resp, "A Tuesday at Cedar Ridge Academy.")
        self.assertContains(resp, "What people actually do here")
        self.assertContains(resp, "One platform. Nothing to babysit.")
        self.assertContains(resp, "One platform that bends to each campus.")
        self.assertContains(resp, "Book a demo")

    def test_landing_nav_has_product_and_solutions_dropdowns(self):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("dropdown-toggle", body)
        # Mega-menu header (replaces legacy compact nav dropdown panel).
        self.assertIn("mkt-mega-menu", body)
        self.assertIn("/platform/student-information-system/", body)
        self.assertIn("/for-private-schools/", body)
        self.assertIn("/offline-first/", body)
        self.assertIn("Platform status", body)
        self.assertIn("/trust/", body)

    def test_landing_includes_platform_visual_assets_without_placeholder_video_urls(self):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("marketing/css/marketing-landing-v2.css", body)
        self.assertIn("mkt-edt-hero__artifact", body)
        self.assertIn("mkt-edt-frieze", body)
        self.assertNotIn("youtube.com/watch?v=YE7VzlLtp-4", body)


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

    def test_platform_admissions_differentiated_layout_and_pipeline_asset(self):
        resp = self.client.get("/platform/admissions/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-mkt-platform-admissions="1"', body)
        self.assertIn("platform-admissions-pipeline.svg", body)
        self.assertIn("data-mkt-admissions-pipeline-visual", body)
        self.assertIn(
            "Turn every inquiry into an organized enrollment journey.", body
        )
        self.assertIn("marketing-platform-admissions.css", body)

    def test_platform_fees_payments_differentiated_layout(self):
        resp = self.client.get("/platform/fees-payments/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-mkt-platform-fees-payments="1"', body)
        self.assertIn("platform-fees-payments-dashboard.svg", body)
        self.assertIn("data-mkt-fees-dashboard-visual", body)
        self.assertIn("data-mkt-fees-connected-handoff", body)
        self.assertIn(
            "Every invoice, receipt, and balance in one finance workspace.", body
        )
        self.assertIn("marketing-platform-fees-payments.css", body)

    def test_platform_parent_portal_differentiated_layout(self):
        resp = self.client.get("/platform/parent-portal/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-mkt-platform-parent-portal="1"', body)
        self.assertIn("platform-parent-mobile-portal.svg", body)
        self.assertIn("data-mkt-parent-portal-visual", body)
        self.assertIn("data-mkt-parent-connected-handoff", body)
        self.assertIn("Give families a clear window into school life.", body)
        self.assertIn("marketing-platform-parent-portal.css", body)

    def test_platform_teacher_portal_differentiated_layout(self):
        resp = self.client.get("/platform/teacher-portal/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-mkt-platform-teacher-portal="1"', body)
        self.assertIn("platform-teacher-workspace.svg", body)
        self.assertIn("data-mkt-teacher-workspace-visual", body)
        self.assertIn("data-mkt-teacher-connected-handoff", body)
        self.assertIn(
            "One classroom workspace for attendance, marks, assignments, and progress.",
            body,
        )
        self.assertIn("marketing-platform-teacher-portal.css", body)


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
class MarketingFullUrlInventoryTests(TestCase):
    """GET every marketing_* route after CMS seed (aligns with validate_marketing_urls --full --seed-cms)."""

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
        call_command("seed_marketing_cms", verbosity=0)

    def tearDown(self):
        self.env.stop()

    def _get(self, path: str):
        with patch(
            "django.test.client.store_rendered_templates",
            _store_rendered_templates_without_context_copy,
        ):
            return self.client.get(path, HTTP_HOST=self.host, follow=True)

    def test_all_inventory_marketing_urls_acceptable_status(self):
        for target in iter_marketing_smoke_targets():
            with self.subTest(name=target.name, path=target.path):
                resp = self._get(target.path)
                self.assertTrue(
                    target.accepts(resp.status_code),
                    f"{target.name} GET {target.path} -> {resp.status_code}, "
                    f"expected one of {sorted(target.ok_statuses)}",
                )

    def test_all_adjacent_marketing_surface_urls_return_200(self):
        for target in iter_marketing_adjacent_smoke_targets():
            with self.subTest(name=target.name, path=target.path):
                resp = self._get(target.path)
                self.assertTrue(
                    target.accepts(resp.status_code),
                    f"{target.name} GET {target.path} -> {resp.status_code}, "
                    f"expected one of {sorted(target.ok_statuses)}",
                )


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

    def test_hero_primary_book_demo_with_product_tour_only(self):
        session = self.client.session
        session["marketing_cta_variant"] = "secondary"
        session.save()
        resp = self.client.get("/marketing/", HTTP_HOST=self.host, secure=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        hero_part = body.split('aria-labelledby="hero-headline"', 1)[1].split(
            'mkt-edt-hero__artifact',
            1,
        )[0]
        self.assertIn("Book a demo", hero_part)
        self.assertIn("See it live", hero_part)
        self.assertNotIn("Start Free Trial", hero_part)

    def test_legacy_hero_variant_b_session_keeps_v2_homepage_stable(self):
        session = self.client.session
        session["marketing_ab_variant"] = "B"
        session.save()
        resp = self.client.get("/marketing/", HTTP_HOST=self.host, secure=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Run your school the way your school actually runs.")
        self.assertContains(resp, 'data-mkt-edition="editorial"')


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingLegacyCanonicalRedirectTests(TestCase):
    """Legacy marketing paths 301 to brief-critical canonical URLs."""

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

    def test_legacy_paths_301_to_canonical(self):
        pairs = (
            ("/guides/", "/resources/guides/"),
            ("/blog/", "/resources/blog/"),
            ("/case-studies/", "/resources/case-studies/"),
            (reverse("institution_k12"), "/solutions/k12-schools/"),
        )
        for src, expected_path in pairs:
            with self.subTest(src=src):
                resp = self.client.get(src, HTTP_HOST=self.host, follow=False)
                self.assertEqual(resp.status_code, 301)
                loc = resp.headers["Location"]
                path = urlparse(loc).path if "://" in loc else loc
                self.assertEqual(
                    path,
                    expected_path,
                    f"Unexpected redirect Location {loc!r} for {src}",
                )

    def test_canonical_brief_paths_return_200(self):
        for path in (
            "/resources/guides/",
            "/resources/case-studies/",
            "/resources/blog/",
            "/solutions/k12-schools/",
        ):
            with self.subTest(path=path):
                r = self.client.get(path, HTTP_HOST=self.host)
                self.assertEqual(r.status_code, 200)


@override_settings(
    ALLOWED_HOSTS=["*"],
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    MARKETING_CONTACT_WEBHOOK_URL=None,
    MARKETING_DEMO_WEBHOOK_URL=None,
)
class MarketingContactSubmitTests(TestCase):
    """Contact POST-only route and redirect query params."""

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

    def test_contact_submit_get_returns_405(self):
        resp = self.client.get(
            reverse("marketing_contact_submit"),
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 405)

    def test_contact_submit_post_with_email_redirects_submitted(self):
        resp = self.client.post(
            reverse("marketing_contact_submit"),
            {
                "name": "Test User",
                "email": "contact-test@example.com",
                "message": "Hello",
            },
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers["Location"]
        self.assertIn(reverse("marketing_contact"), loc)
        self.assertIn("submitted=1", loc)

    def test_contact_submit_post_without_email_redirects_error(self):
        resp = self.client.post(
            reverse("marketing_contact_submit"),
            {"name": "Test User", "message": "Hello"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=1", resp.headers["Location"])


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingInstitutionPremiumVisualTests(TestCase):
    """Institution premium layer uses self-hosted static artwork + alt text."""

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

    def test_k12_schools_stock_visual_is_static_with_alt(self):
        resp = self.client.get("/solutions/k12-schools/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "/static/images/marketing/module-academics.svg")
        self.assertContains(resp, 'alt="Illustration of K–12 academics')


class ExperienceControlMarketingRegistryTests(SimpleTestCase):
    """Experience_control roster: public marketing surfaces resolve on public_urls."""

    def test_roster_marketing_home_and_platform_page_reverse(self):
        from apps.platform_runtime.tests.experience_control_registry import (
            EXPERIENCE_CONTROL_SCREENS,
            reverse_screen,
        )

        for key in ("marketing_homepage", "marketing_platform_page"):
            row = next(r for r in EXPERIENCE_CONTROL_SCREENS if r["id"] == key)
            reverse_screen(row)

    def test_roster_public_urls_procurement_surfaces_reverse(self):
        from apps.platform_runtime.tests.experience_control_registry import (
            EXPERIENCE_CONTROL_SCREENS,
            reverse_screen,
        )

        for key in (
            "marketing_procurement_checklist",
            "marketing_implementation_assurance",
            "marketing_security_packet_request",
        ):
            row = next(r for r in EXPERIENCE_CONTROL_SCREENS if r["id"] == key)
            path = reverse_screen(row)
            self.assertTrue(path.startswith("/"), msg=path)
