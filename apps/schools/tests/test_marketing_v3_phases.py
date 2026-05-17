"""Marketing v3 phase 1–4 regression tests."""

from __future__ import annotations

from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.schools.marketing_v3_surfaces import (
    MARKETING_PLATFORM_TO_VERB_REDIRECTS,
    marketing_module_rail_modules,
    marketing_navbar_verb_primary,
    marketing_verb_nav_enabled,
)


class MarketingVerbNavTest(SimpleTestCase):
    def test_verb_nav_enabled_by_default(self) -> None:
        self.assertTrue(marketing_verb_nav_enabled())

    def test_verb_nav_has_five_verbs(self) -> None:
        labels = [x["label"] for x in marketing_navbar_verb_primary()]
        self.assertIn("Run", [str(x) for x in labels])
        self.assertIn("Teach", [str(x) for x in labels])
        self.assertGreaterEqual(len(labels), 5)

    def test_platform_to_verb_redirect_map_nonempty(self) -> None:
        self.assertGreaterEqual(len(MARKETING_PLATFORM_TO_VERB_REDIRECTS), 5)

    def test_differentiated_platform_templates_registered(self) -> None:
        from apps.schools.marketing_views import _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES

        for slug in (
            "platform-admissions",
            "platform-attendance",
            "platform-analytics",
            "platform-communications",
            "platform-fees-payments",
            "platform-workflows",
            "platform-offline-first",
            "platform-security",
            "platform-student-information-system",
            "platform-student-portal",
            "platform-grading-report-cards",
        ):
            self.assertIn(slug, _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES)

    def test_why_switch_and_pricing_v3_templates_registered(self) -> None:
        from apps.schools.marketing_views import _MARKETING_PAGE_TYPE_TEMPLATES

        self.assertEqual(
            _MARKETING_PAGE_TYPE_TEMPLATES.get("why-switch"),
            "marketing/pages/type_why_switch.html",
        )
        self.assertEqual(
            _MARKETING_PAGE_TYPE_TEMPLATES.get("pricing"),
            "marketing/pages/type_pricing.html",
        )
        self.assertEqual(
            _MARKETING_PAGE_TYPE_TEMPLATES.get("trust-center"),
            "marketing/pages/type_trust_center.html",
        )

    def test_more_pages_and_developers_v3_templates_registered(self) -> None:
        from apps.schools.marketing_views import (
            _MARKETING_PAGE_TYPE_TEMPLATES,
            _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES,
        )

        for slug, tpl in (
            ("contact", "marketing/pages/type_contact.html"),
            ("demo", "marketing/pages/type_demo.html"),
            ("company", "marketing/pages/type_company.html"),
            ("resources", "marketing/pages/type_resources_hub.html"),
            ("developers", "marketing/pages/type_developers.html"),
        ):
            self.assertEqual(_MARKETING_PAGE_TYPE_TEMPLATES.get(slug), tpl)
        for slug in (
            "platform-integrations",
            "platform-runtime",
            "platform-control-plane",
            "platform-education-os",
            "platform-marketplace",
            "platform-migration-cloud",
        ):
            self.assertIn(slug, _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES)

    def test_platform_fallback_uses_generic_not_legacy_detail(self) -> None:
        from apps.schools.marketing_views import _marketing_page_type_template

        self.assertEqual(
            _marketing_page_type_template("platform-legacy-unknown-slug"),
            "marketing/pages/type_platform_generic.html",
        )
        legacy = Path("templates/marketing/pages/type_platform_detail.html")
        self.assertFalse(legacy.exists(), "retired legacy platform detail shell")
        legacy_trust = Path("templates/marketing/trust_center.html")
        self.assertFalse(legacy_trust.exists(), "retired legacy trust_center shell")

    def test_solutions_persona_urls_point_to_dedicated_routes(self) -> None:
        from apps.schools.marketing_v3_surfaces import marketing_solutions_personas

        personas = marketing_solutions_personas()
        self.assertEqual(len(personas), 5)
        for p in personas:
            self.assertIn(f"/solutions/{p['slug']}/", p["url"])
            self.assertGreaterEqual(len(p.get("bullets") or []), 2)

    def test_home_hero_voice_retired(self) -> None:
        text = Path("templates/schools/marketing_landing_v2.html").read_text(encoding="utf-8")
        self.assertNotIn("mkt-edt-hero__voice", text)


class MarketingShortcutsI18nWiringTest(SimpleTestCase):
    def test_shells_include_shortcuts_i18n_before_registry(self) -> None:
        for rel in (
            "templates/portal_base.html",
            "templates/base.html",
            "templates/control_plane_skeleton.html",
            "templates/marketing/base_marketing.html",
            "templates/admin/base_site.html",
        ):
            text = Path(rel).read_text(encoding="utf-8")
            self.assertIn("rmc_shortcuts_i18n.html", text, rel)
            idx_i18n = text.find("rmc_shortcuts_i18n.html")
            idx_reg = text.find("rmc-shortcuts-registry.js")
            self.assertGreater(idx_i18n, -1, rel)
            self.assertGreater(idx_reg, -1, rel)
            self.assertLess(idx_i18n, idx_reg, rel)


class MarketingVerbHubLinksTest(SimpleTestCase):
    def test_verb_hub_links_nonempty_for_run_and_teach(self) -> None:
        from apps.schools.marketing_v3_surfaces import marketing_verb_hub_links

        run_links = marketing_verb_hub_links("run")
        teach_links = marketing_verb_hub_links("teach")
        self.assertGreaterEqual(len(run_links), 3)
        self.assertGreaterEqual(len(teach_links), 2)
        self.assertTrue(any("/run/admissions/" in (x.get("path") or "") for x in run_links))


@override_settings(ROOT_URLCONF="config.public_urls", ALLOWED_HOSTS=["runmycampus.com", "testserver"])
class MarketingTrustAndVerbRoutesHttpTest(TestCase):
    def setUp(self) -> None:
        self.client = Client(HTTP_HOST="runmycampus.com")

    def test_trust_and_verb_pages_return_v3_markers(self) -> None:
        for path in (
            "/trust/",
            "/why-switch/",
            "/pricing/",
            "/teach/workspace/",
            "/communicate/announcements/",
            "/run/workflows/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, msg=path)
                self.assertTrue(
                    b"mkt-v3-page" in response.content
                    or b"mkt-v3-verb-hub" in response.content
                    or b"mkt-v3-archetype" in response.content,
                    msg=path,
                )

    def test_platform_workflows_redirects_to_run_workflows(self) -> None:
        response = self.client.get("/platform/workflows/", HTTP_HOST="runmycampus.com")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.headers.get("Location", "").endswith("/run/workflows/"))


class MarketingModuleRailTest(SimpleTestCase):
    def test_eight_modules(self) -> None:
        mods = marketing_module_rail_modules()
        self.assertEqual(len(mods), 8)
        self.assertEqual(mods[0]["index"], "1.0")


class MarketingHomeNineSectionsTest(SimpleTestCase):
    def test_home_has_nine_primary_sections(self) -> None:
        from pathlib import Path

        text = Path("templates/schools/marketing_landing_v2.html").read_text(encoding="utf-8")
        # Hero + ROI + walkthrough + globe + switching + compare + pricing + voices + close
        self.assertIn("mkt-edt-hero", text)
        self.assertIn("_bell_clock_sticky.html", text)
        self.assertIn("_persona_tabs.html", text)
        self.assertIn("mkt-edt-roi", text)
        self.assertIn("mkt-edt-walkthrough", text)
        self.assertIn("mkt-edt-globe", text)
        self.assertIn("mkt-edt-switching", text)
        self.assertIn("mkt-edt-compare", text)
        self.assertIn("mkt-edt-voices--compact", text)
        self.assertIn("mkt-edt-close", text)
        self.assertNotIn("mkt-edt-lens", text)
        self.assertNotIn("mkt-edt-jobs", text)


@override_settings(ROOT_URLCONF="config.public_urls", ALLOWED_HOSTS=["runmycampus.com", "testserver"])
class MarketingDifferentiatedVerbRoutesHttpTest(TestCase):
    """Verb-canonical routes must render tranche-2 differentiated platform layouts."""

    def setUp(self) -> None:
        self.client = Client(HTTP_HOST="runmycampus.com")

    def test_verb_routes_render_differentiated_markers_and_css(self) -> None:
        cases = (
            ("/pay/fees/", b"data-mkt-platform-fees-payments", b"marketing-platform-fees-payments.css"),
            ("/communicate/inbox/", b"data-mkt-platform-parent-portal", b"marketing-platform-parent-portal.css"),
            ("/teach/workspace/", b"data-mkt-platform-teacher-portal", b"marketing-platform-teacher-portal.css"),
            ("/run/analytics/", b"data-mkt-platform-analytics", b"marketing-platform-analytics.css"),
        )
        for path, marker, css in cases:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, msg=path)
                body = response.content
                self.assertIn(marker, body, msg=path)
                self.assertIn(css, body, msg=path)

    def test_platform_security_renders_differentiated_layout(self) -> None:
        response = self.client.get("/platform/security/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"data-mkt-platform-security", response.content)
        self.assertIn(b"marketing-platform-security.css", response.content)


@override_settings(ROOT_URLCONF="config.public_urls", ALLOWED_HOSTS=["runmycampus.com", "testserver"])
class MarketingV3PagesHttpTest(TestCase):
    """Smoke v3 backlog pages on canonical marketing host."""

    def setUp(self) -> None:
        self.client = Client(HTTP_HOST="runmycampus.com")

    def test_v3_more_pages_and_persona_return_200(self) -> None:
        for path in (
            "/contact/",
            "/demo/",
            "/company/",
            "/resources/",
            "/developers/",
            "/solutions/head/",
            "/platform/integrations/",
            "/grow/marketplace/",
            "/grow/migration/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, msg=path)
                self.assertTrue(
                    b"mkt-v3-page" in response.content
                    or b"mkt-v3-archetype" in response.content
                    or b"mkt-v3-verb-hub" in response.content,
                    msg=path,
                )


class MarketingPlatformVerbRedirectsTest(SimpleTestCase):
    """Legacy /platform/* module paths must inline 301 RedirectView (not marketing_page)."""

    def test_platform_paths_use_redirectview_inline(self) -> None:
        text = Path("config/public_urls.py").read_text(encoding="utf-8")
        for src, dst in MARKETING_PLATFORM_TO_VERB_REDIRECTS.items():
            idx = text.find(f'"{src}"')
            self.assertGreater(idx, -1, f"missing route for {src}")
            window = text[idx : idx + 280]
            self.assertIn(
                "RedirectView.as_view",
                window,
                f"{src} must use RedirectView inline (appended patterns lose to earlier routes)",
            )
            self.assertIn(
                f'"/{dst.rstrip("/")}/"',
                window,
                f"{src} must target /{dst}",
            )
