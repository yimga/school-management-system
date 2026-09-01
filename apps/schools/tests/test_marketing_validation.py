"""
Marketing URL resolution and smoke tests aligned with validate_marketing_urls and MARKETING_NON_NEGOTIABLES.
Ensures all key marketing routes resolve and return 200 on canonical host; landing renders required visual assets.
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

from django.conf import settings
from django.test.client import ContextList
from django.test import (
    Client,
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.core.management import call_command, get_commands
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


class MarketingPublicRouteTransactionCase(TransactionTestCase):
    """Committed writes keep file-backed SQLite public route sweeps moving."""


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
    "marketing_security_compliance",
    "marketing_trust_center",
    "marketing_platform_security",
    "marketing_trust_coppa",
    "marketing_trust_accessibility",
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
    "developer_hub",
    "developer_console",
    "developer_public_api_docs",
    "marketing_trust_dedicated",
    "marketing_security_compliance",
    "marketing_trust_center",
    "marketing_platform_security",
    "marketing_trust_coppa",
    "marketing_trust_accessibility",
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
class MarketingSmokeTests(MarketingPublicRouteTransactionCase):
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
class MarketingLandingContextTests(MarketingPublicRouteTransactionCase):
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
        # v3 marketing redesign (Phase 0/1): home now uses schoolhouse + v3
        # primitives. The legacy editorial-only sections (crests, frieze, job
        # artifact, lens panel) were retired during the voices+walkthrough
        # repositioning; the remaining stable v3 markers are the hero artifact,
        # the walkthrough reel, the bell-clock sticky pin, persona tabs, and
        # the product-proof block.
        self.assertContains(resp, "marketing/css/marketing-landing-v2.css")
        self.assertContains(resp, "mkt-edt-hero__artifact")
        self.assertContains(resp, "mkt-edt-walkthrough__reel")
        self.assertContains(resp, "mkt-v3-bell-clock")
        self.assertContains(resp, "mkt-v3-persona-tabs")
        self.assertContains(resp, "mkt-v3-product-proof")

    def test_landing_renders_admissions_flow_post_enrollment_and_what_you_get(self):
        """MARKETING_PAGE_AUDIT: context keys must surface on HTML (was context-only).

        v3 redesign (Phase 0/1) replaced the static legacy hero copy with a
        rotating headline + Tuesday eyebrow + cedar-ridge narrative spine.
        Stable markers: rotating-headline prefix, Tuesday eyebrow, primary CTA,
        compare-block "One platform that bends..." copy, and the v3 bell-clock
        sticky pin (verifies the Tuesday narrative is wired).
        """
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Run every school day from one operating system")
        self.assertContains(resp, "Tuesday · Cedar Ridge Academy")
        self.assertContains(resp, "One platform that bends to each campus.")
        self.assertContains(resp, "Book a demo")
        self.assertContains(resp, "mkt-v3-bell-clock")

    def test_landing_nav_has_product_and_solutions_dropdowns(self):
        """Enterprise IA: Platform / Solutions / Why / Pricing / Resources / More."""
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("dropdown-toggle", body)
        self.assertIn("mkt-mega-menu", body)
        self.assertIn(">Platform<", body)
        self.assertIn(">Solutions<", body)
        self.assertIn(">Why RunMyCampus<", body)
        self.assertIn(">Resources<", body)
        self.assertIn(">More<", body)
        self.assertIn("Operating journey", body)
        self.assertIn("Inquiry → Enrollment → Attendance → Fees", body)
        self.assertIn("/pricing/", body)
        self.assertIn("Platform status", body)
        self.assertIn("/trust/", body)

    def test_landing_includes_platform_visual_assets_without_placeholder_video_urls(self):
        """v3 redesign (Phase 0/1): editorial frieze section retired; the
        product-proof block + walkthrough reel now carry the visual rhythm."""
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("marketing/css/marketing-landing-v2.css", body)
        self.assertIn("mkt-edt-hero__artifact", body)
        self.assertIn("mkt-v3-product-proof", body)
        self.assertIn("mkt-edt-walkthrough__reel", body)
        self.assertNotIn("youtube.com/watch?v=YE7VzlLtp-4", body)


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingPageExtrasTests(MarketingPublicRouteTransactionCase):
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
        self.assertContains(resp, "mkt-v3-platform-overview")
        self.assertContains(resp, "data-mkt-module-rail")

    def test_products_analytics_page_returns_200_and_has_visual(self):
        resp = self.client.get("/products/analytics/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-rmc-page-slug")
        self.assertContains(resp, "products-analytics")
        self.assertContains(resp, "platform-diagram-marketing.svg")

    def test_onboard_wizard_returns_200(self):
        resp = self.client.get("/onboard/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)

    def test_platform_module_urls_render_platform_detail_pages(self):
        """Required platform routes stay clean instead of redirecting to verb hubs."""
        cases = (
            "/platform/student-information-system/",
            "/platform/admissions/",
            "/platform/attendance/",
            "/platform/fees-payments/",
            "/platform/grading-report-cards/",
            "/platform/parent-portal/",
            "/platform/teacher-portal/",
            "/platform/student-portal/",
            "/platform/communications/",
            "/platform/analytics/",
            "/platform/workflows/",
            "/platform/offline-first/",
            "/platform/security/",
        )
        for path in cases:
            with self.subTest(path=path):
                resp = self.client.get(path, HTTP_HOST=self.host)
                self.assertEqual(resp.status_code, 200, msg=path)
                self.assertContains(resp, "data-mkt-archetype")

    def test_platform_student_portal_still_renders_detail_page(self):
        """The detail page renders with the visual that is ITS OWN.

        This asserted ``mkt-v3-dashboard-frame`` until now and had been red
        for it. The frame was removed from this page on purpose in
        b2499d8ac, whose message gives the reason: ``_dashboard_frame`` was
        being fed a generic artifact that did not match the page it sat on.
        Here it was ``_artifact_parent_phone_compact`` -- a PARENT's phone
        under a STUDENT portal heading. Grading, workflows and offline-first
        lost the same mismatched frame in that commit; only this assertion
        was left behind, so it has failed ever since while the page was
        correct. 18 of the 21 type_platform_*.html pages carry no dashboard
        frame at all, so its presence was never the detail-page contract.

        Re-pointed at the purpose-built student SVG that replaced it. The
        negative pins the defect rather than the removal: a dashboard frame
        may legitimately come back, but not one showing a parent's phone.
        """
        resp = self.client.get("/platform/student-portal/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-mkt-archetype")
        self.assertContains(resp, "mkt-page-platform-student-portal")
        self.assertContains(resp, "data-mkt-platform-visual")
        # No ".svg": a hashed static URL carries a digest before the
        # extension, and this must hold under either storage backend.
        self.assertContains(resp, "platform-student-self-service")
        self.assertNotContains(
            resp,
            "parent-phone-compact-title",
            msg_prefix="the student portal is showing a parent's phone again",
        )


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
class MarketingRegionalJsonIntegrationTests(MarketingPublicRouteTransactionCase):
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


#: Marketing route names that exist on the DEV urlconf (config.urls) and are
#: not mounted on the public marketing host. iter_marketing_smoke_targets()
#: reverses against get_resolver(), which outside a request is
#: settings.ROOT_URLCONF -- the dev superset -- while the GET below resolves
#: config.public_urls. So these come back 404 for a HOST reason, not a dead
#: route, and reporting them as ordinary failures buried two real content
#: regressions in the same module.
#:
#: Each entry carries its reason and is pinned in BOTH directions: the test
#: asserts these 404 on the marketing host, so a route that later becomes
#: public fails here until its entry is removed. A THIRD divergence fails
#: outright rather than being absorbed.
_DEV_ONLY_MARKETING_ROUTES = {
    "marketing_threshold_era_preview": (
        "deprecated stakeholder preview -- its own view docstring says use "
        "/storefront/ instead, and it is served noindex, nofollow"
    ),
    "marketing_compare_replacement": (
        "/compare/replacement/ carries page_slug compare-replacement, which has "
        "no COMPARE_PAGE_DEFINITIONS entry (power-school, blackbaud and "
        "infinite-campus are the three that do)"
    ),
}


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingFullUrlInventoryTests(MarketingPublicRouteTransactionCase):
    """GET every marketing_* route after CMS seed (aligns with validate_marketing_urls --full --seed-cms)."""

    # seed_marketing_cms writes CMS rows before the request sweep. TestCase keeps
    # those writes inside an open transaction, which can wedge file-backed SQLite
    # when request-time marketing code opens another connection under --keepdb.

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
                reason = _DEV_ONLY_MARKETING_ROUTES.get(target.name)
                if reason is not None:
                    self.assertEqual(
                        resp.status_code,
                        404,
                        f"{target.name} is now served on the marketing host; "
                        f"remove it from _DEV_ONLY_MARKETING_ROUTES ({reason})",
                    )
                    continue
                self.assertTrue(
                    target.accepts(resp.status_code),
                    f"{target.name} GET {target.path} -> {resp.status_code}, "
                    f"expected one of {sorted(target.ok_statuses)}",
                )

    def test_every_dev_only_route_is_still_in_the_inventory(self):
        """Otherwise a renamed route leaves a dead entry nobody notices."""
        names = {t.name for t in iter_marketing_smoke_targets()}
        for name in _DEV_ONLY_MARKETING_ROUTES:
            with self.subTest(name=name):
                self.assertIn(
                    name,
                    names,
                    f"{name} no longer reverses at all -- delete its entry",
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


class MarketingAbVariantTests(MarketingPublicRouteTransactionCase):
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
        """v3 redesign (Phase 0/1): legacy A/B variant B should still resolve
        to the home page. The exact-string hero copy was replaced by the
        rotating-headline component; the editorial body marker remains."""
        session = self.client.session
        session["marketing_ab_variant"] = "B"
        session.save()
        resp = self.client.get("/marketing/", HTTP_HOST=self.host, secure=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Run every school day from one operating system")
        self.assertContains(resp, 'data-mkt-edition="editorial"')


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingLegacyCanonicalRedirectTests(MarketingPublicRouteTransactionCase):
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

    def test_case_studies_honest_region_labels_not_school_a(self):
        resp = self.client.get("/resources/case-studies/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("data-mkt-case-studies-honest", body)
        self.assertIn("Cameroon", body)
        self.assertNotIn('"School A"', body)


@override_settings(
    ALLOWED_HOSTS=["*"],
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    MARKETING_CONTACT_WEBHOOK_URL=None,
    MARKETING_DEMO_WEBHOOK_URL=None,
)
class MarketingContactSubmitTests(MarketingPublicRouteTransactionCase):
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
class MarketingInstitutionPremiumVisualTests(MarketingPublicRouteTransactionCase):
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
        self.assertContains(resp, 'alt="Illustration of K-12 academics')


class DeveloperHubPublicUrlconfTests(MarketingPublicRouteTransactionCase):
    """Developer hub must render on runmycampus.com (config.public_urls), not 500 on reverse()."""

    # The developer sweep renders several public-host pages per test. Keep it
    # outside TestCase's open transaction so file-backed SQLite request hooks
    # cannot wait on their own route-sweep transaction under --keepdb.

    def test_developer_hub_reverses_and_renders_on_public_host(self):
        from django.test import Client
        from django.urls import reverse

        with patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        ):
            for name in ("developer_hub", "developer_console", "developer_public_api_docs"):
                path = reverse(name, urlconf="config.public_urls")
                self.assertTrue(path.startswith("/"), msg=path)
            resp = Client().get("/developer/", HTTP_HOST="runmycampus.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "RunMyCampus for developers")
        self.assertContains(resp, "developer-section-nav")

    def test_developer_console_prompts_manager_sign_in_for_api_keys(self):
        from django.test import Client

        with patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        ):
            resp = Client().get("/developer/console/", HTTP_HOST="runmycampus.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "API keys (authenticated)")
        self.assertContains(resp, "Sign in on manager")
        self.assertContains(resp, "data-rmc-developer-api-keys")

    def test_developer_manifest_json_on_public_host(self):
        with patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        ):
            resp = Client().get("/api/v2/manifest.json", HTTP_HOST="runmycampus.com")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/json")

    def test_all_developer_pages_render_with_section_nav(self):
        paths = (
            "/developer/",
            "/developer/console/",
            "/developer-portal/",
            "/developer-portal/sdk/",
            "/developer-portal/sandbox/",
            "/developers/",
            "/developers/api/",
            "/developers/webhooks/",
            "/developers/api-docs/",
        )
        with patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        ):
            client = Client()
            for path in paths:
                resp = client.get(path, HTTP_HOST="runmycampus.com")
                self.assertEqual(resp.status_code, 200, msg=path)
                self.assertContains(resp, "developer-section-nav", msg_prefix=path)

    def test_developer_sandbox_renders_preview_frame(self):
        with patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        ):
            resp = Client().get("/developer-portal/sandbox/", HTTP_HOST="runmycampus.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "developer-app-sandbox-frame")
        # This asserted ``ensure_demo_environment`` and had been red for it.
        # 734de5226 changed the slab to ``ensure_developer_sandbox_tenant`` --
        # a purpose-built command that provisions the sandbox tenant, and
        # added an 'Open sandbox tenant' link beside it -- without updating
        # the test. The page was right; the assertion was stale.
        #
        # Asserting the new NAME would only move the staleness one rename
        # along. The page hands a developer a line to paste, so the contract
        # is that the line RUNS: every manage.py command printed here is
        # read back off the rendered page and looked up in the real command
        # registry. Now a rename fails whichever side moves first.
        printed = re.findall(r"manage\.py ([a-z_][a-z0-9_]+)", resp.content.decode())
        self.assertTrue(
            printed, "the sandbox page no longer shows a command to run"
        )
        registry = get_commands()
        for name in sorted(set(printed)):
            with self.subTest(command=name):
                self.assertIn(
                    name,
                    registry,
                    f"/developer-portal/sandbox/ tells a developer to run "
                    f"manage.py {name}, which is not a management command",
                )
        self.assertIn("ensure_developer_sandbox_tenant", printed)


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingLocalFirstTiersTests(MarketingPublicRouteTransactionCase):
    """Tier 2–3: security-packet annex, honest case studies, enterprise + marketplace copy."""

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

    def test_security_packet_jurisdiction_and_country_annex(self):
        resp = self.client.get(
            reverse("marketing_security_packet_request") + "?jurisdiction=ndpr-ng",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("data-mkt-security-country-annex", body)
        self.assertIn("Which jurisdiction governs your student records", body)
        self.assertIn("Nigeria", body)
        self.assertIn("mkt-security-packet-annex.js", body)

    def test_demo_compliance_jurisdiction_picker(self):
        resp = self.client.get(reverse("marketing_demo"), HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Which jurisdiction governs your student records", resp.content)
        self.assertIn(b'compliance_jurisdiction', resp.content)

    def test_pricing_enterprise_governance_layer_narrative(self):
        resp = self.client.get("/pricing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"governance layer", resp.content)

    def test_marketplace_activate_per_campus_copy(self):
        resp = self.client.get("/grow/marketplace/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"activate per campus", resp.content.lower())

    def test_landing_scale_signal_with_illustrative_disclaimer(self):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("mkt-scale-signal", body)
        self.assertIn("Illustrative scale signal", body)


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
