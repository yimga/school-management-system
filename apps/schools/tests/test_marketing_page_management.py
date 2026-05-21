"""Marketing page-management contracts for the public operating-system front."""

import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


MAJOR_PLATFORM_SLUGS = (
    "platform-admissions",
    "platform-fees-payments",
    "platform-parent-portal",
    "platform-teacher-portal",
    "platform-analytics",
    "platform-security",
    "platform-student-information-system",
    "platform-attendance",
    "platform-grading-report-cards",
    "platform-communications",
    "platform-workflows",
    "platform-offline-first",
    "platform-student-portal",
)


class MarketingPageManagementContractTests(SimpleTestCase):
    def _content(self, slug):
        path = Path(settings.BASE_DIR) / "config" / "marketing_content" / f"{slug}.json"
        self.assertTrue(path.exists(), f"Missing marketing content file for {slug}")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_major_platform_pages_have_operating_system_story_contract(self):
        for slug in MAJOR_PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                data = self._content(slug)
                extras = data.get("extras") or {}
                self.assertTrue(data.get("seo_title"))
                self.assertTrue(data.get("seo_description"))
                self.assertGreaterEqual(len(data.get("segments") or []), 3)
                self.assertTrue(extras.get("problem_section"), f"{slug} needs pain story")
                self.assertTrue(extras.get("workflow_steps"), f"{slug} needs workflow")
                self.assertTrue(extras.get("benefits_by_role"), f"{slug} needs role impact")
                self.assertTrue(extras.get("related_platform_links"), f"{slug} needs next links")
                self.assertTrue(
                    extras.get("diagram_path")
                    or extras.get("data_viz_path")
                    or extras.get("stock_photo_static")
                    or extras.get("stock_photo_url"),
                    f"{slug} needs visual proof",
                )

    def test_referenced_static_marketing_assets_exist(self):
        static_root = Path(settings.BASE_DIR) / "static"
        for path in sorted((Path(settings.BASE_DIR) / "config" / "marketing_content").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            extras = data.get("extras") or {}
            for key in ("diagram_path", "data_viz_path", "stock_photo_static"):
                value = extras.get(key)
                if value:
                    with self.subTest(file=path.name, key=key, value=value):
                        self.assertTrue((static_root / value).exists())
            for stop in extras.get("product_tour_stops") or []:
                value = stop.get("static_visual")
                if value:
                    with self.subTest(file=path.name, key="product_tour_stops", value=value):
                        self.assertTrue((static_root / value).exists())

    def test_analytics_and_page_management_artifacts_exist(self):
        required_paths = (
            "static/marketing/js/marketing-analytics.js",
            "templates/marketing/partials/marketing_analytics.html",
            "docs/marketing_front_page_management.md",
            "docs/generated/marketing_analytics_event_contract.md",
        )
        for rel in required_paths:
            with self.subTest(path=rel):
                self.assertTrue((Path(settings.BASE_DIR) / rel).exists())

    def test_public_marketing_templates_do_not_use_placeholder_hash_links(self):
        roots = (
            Path(settings.BASE_DIR) / "templates" / "marketing",
            Path(settings.BASE_DIR) / "templates" / "schools",
        )
        for root in roots:
            for path in root.rglob("*.html"):
                if not path.name.startswith("marketing") and "marketing" not in str(path):
                    continue
                with self.subTest(path=path.relative_to(settings.BASE_DIR)):
                    self.assertNotIn('href="#"', path.read_text(encoding="utf-8"))

    def test_home_walkthrough_is_not_fake_video_when_source_disabled(self):
        home = (
            Path(settings.BASE_DIR)
            / "templates"
            / "schools"
            / "marketing_landing_v2.html"
        ).read_text(encoding="utf-8")
        portal = (
            Path(settings.BASE_DIR)
            / "templates"
            / "marketing"
            / "components"
            / "_video_portal.html"
        ).read_text(encoding="utf-8")
        self.assertIn("show_video_source=False", home)
        self.assertNotIn("<source src=\"\"", home + portal)
        self.assertNotIn("data-mkt-walkthrough-play", home)
        self.assertIn("Animated product preview", portal)

    def test_demo_and_contact_forms_route_buyer_intent(self):
        demo = (
            Path(settings.BASE_DIR)
            / "templates"
            / "marketing"
            / "components"
            / "_marketing_demo_form.html"
        ).read_text(encoding="utf-8")
        contact = (
            Path(settings.BASE_DIR)
            / "templates"
            / "marketing"
            / "components"
            / "_marketing_contact_form.html"
        ).read_text(encoding="utf-8")
        self.assertIn("interest_migration", demo)
        self.assertIn("interest_offline", demo)
        self.assertIn("interest_procurement", demo)
        self.assertIn("developer-integration", contact)
        self.assertIn('data-cta="contact-submit"', contact)

    def test_solutions_hub_is_a_buyer_world_map(self):
        data = self._content("solutions")
        segment_titles = [segment["title"] for segment in data.get("segments") or []]
        self.assertEqual(
            segment_titles,
            [
                "Private Schools",
                "International Schools",
                "K-12 Schools",
                "Multi-Campus Groups",
                "Faith-Based Schools",
                "Growing School Networks",
            ],
        )

        template = (
            Path(settings.BASE_DIR)
            / "templates"
            / "marketing"
            / "pages"
            / "solutions_overview.html"
        ).read_text(encoding="utf-8")
        self.assertIn("data-mkt-buyer-world-hub", template)
        self.assertIn("solution_buyer_worlds", template)
        self.assertNotIn("Five roles. Five Tuesdays.", template)
        self.assertNotIn("data-mkt-persona-tabs", template)


class MarketingAnalyticsContractTests(SimpleTestCase):
    def test_analytics_javascript_keeps_allowed_anonymous_field_contract(self):
        text = (
            Path(settings.BASE_DIR)
            / "static"
            / "marketing"
            / "js"
            / "marketing-analytics.js"
        ).read_text(encoding="utf-8")
        for field in (
            "event_name",
            "page_path",
            "page_type",
            "page_slug",
            "cta_label",
            "cta_location",
            "menu_name",
            "link_label",
            "link_target",
            "form_name",
            "form_stage",
            "plan_name",
            "resource_type",
            "scroll_depth",
            "timestamp",
        ):
            self.assertIn(field, text)
        for forbidden in ("csrf", "session", "phone:", "email:", "student_name", "message:"):
            self.assertNotIn(forbidden, text.lower())

    def test_marketing_shell_wires_analytics_config_and_local_script(self):
        base = (Path(settings.BASE_DIR) / "templates" / "marketing" / "base_marketing.html").read_text(
            encoding="utf-8"
        )
        partial = (
            Path(settings.BASE_DIR)
            / "templates"
            / "marketing"
            / "partials"
            / "marketing_analytics.html"
        ).read_text(encoding="utf-8")
        self.assertIn("marketing/partials/marketing_analytics.html", base)
        self.assertIn("rmc-marketing-analytics-config", partial)
        self.assertIn("marketing/js/marketing-analytics.js", partial)

    def test_cta_menu_and_form_tracking_hooks_are_present(self):
        header = (Path(settings.BASE_DIR) / "templates" / "marketing" / "marketing_header.html").read_text(
            encoding="utf-8"
        )
        core = (
            Path(settings.BASE_DIR)
            / "templates"
            / "marketing"
            / "partials"
            / "marketing_inner_core.html"
        ).read_text(encoding="utf-8")
        footer = (Path(settings.BASE_DIR) / "templates" / "marketing" / "marketing_footer.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-menu-link", header)
        self.assertIn('data-form-name="contact"', core)
        self.assertIn('data-form-name="demo"', core)
        self.assertIn('data-form-name="newsletter"', footer)

    def test_footer_solution_links_follow_buyer_worlds(self):
        footer = (Path(settings.BASE_DIR) / "templates" / "marketing" / "marketing_footer.html").read_text(
            encoding="utf-8"
        )
        for route_name in (
            "marketing_solutions_private_schools",
            "marketing_solutions_international_schools",
            "marketing_solutions_k12_schools",
            "marketing_solutions_multi_campus",
            "marketing_solutions_faith_based_schools",
            "marketing_solutions_growing_school_networks",
        ):
            self.assertIn(route_name, footer)
        for retired_route in (
            "marketing_solutions_higher_ed",
            "marketing_solutions_k12_districts",
            "role_teachers",
            "role_parents",
        ):
            self.assertNotIn(retired_route, footer)
