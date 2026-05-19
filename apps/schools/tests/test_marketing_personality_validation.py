"""

Personality validation — distinction, seeds, and HTTP smoke for view-layer map.



Maps the advisory board view-layer spec (Next.js page.tsx names) to Django personalities.

"""

from __future__ import annotations



import json

import re

import unittest

from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import NoReverseMatch, resolve, reverse



from apps.schools.marketing_page_definitions import MARKETING_PAGE_DEFINITIONS

from apps.schools.marketing_personality import (

    VIEW_LAYER_SLUGS,

    all_marketing_personality_ids,

    personality_accent_signature,

    resolve_marketing_personality,

)

from apps.schools.marketing_personality_seeds import seed_for_personality

from apps.schools.marketing_view_layer_pages import VIEW_LAYER_MARKETING_PAGE_SLUGS

from apps.schools.marketing_views import marketing_page



# Advisory view-layer keys → Django URL name + expected viz_engine substring

VIEW_LAYER_ROUTE_MAP: dict[str, tuple[str, str]] = {

    "platform-hub": ("marketing_platform", "run-gauge"),

    "about": ("marketing_about", "timeline-corporate"),

    "careers": ("marketing_careers", "stack-selector"),

    "brand-assets": ("marketing_brand_assets", "brand-swatches"),

    "app-marketplace": ("marketing_app_marketplace", "app-catalog"),

    "developer-apis": ("marketing_developers", "api-playground"),

    "solutions/higher-ed": ("marketing_solutions_higher_ed", "provost-research"),

    "solutions/k12-districts": ("marketing_solutions_k12_districts", "board-compliance"),

    "portal-login": ("marketing_portal_login", "secure-gateway"),

    "request-demo": ("marketing_demo", "wizard-steps"),

    "pricing-matrix": ("marketing_pricing", "pricing-matrix"),

    "implementation-timelines": ("marketing_implementation_timelines", "gantt-rollout"),

    "find-campus-portal": ("marketing_find_campus_portal", "geo-finder"),

    "teacher-workspace": ("marketing_platform_teacher_portal", "classroom-roster"),

    "training-academies": ("marketing_training_academies", "lms-progress"),

    "teacher-communities": ("marketing_teacher_communities", "thread-board"),

    "lesson-planning-templates": ("marketing_lesson_planning", "template-canvas"),

    "parent-access-guide": ("marketing_platform_parent_portal", "family-guide"),

    "student-portal-overview": ("marketing_platform_student_portal", "gamified-learner"),

    "system-status": ("status", "incident-monitor"),

    "infrastructure-map": ("marketing_infrastructure_map", "infra-map"),

    "trust-security-center": ("marketing_trust_center", "trust-ledger"),

    "security-matrix": ("marketing_security_matrix", "rbac-matrix"),

    "support-knowledge-base": ("marketing_resources_help_center", "kb-search"),

    "procurement-docs": ("marketing_procurement_docs", "procurement-repo"),

    "legal-compliance/ferpa": ("marketing_legal_ferpa", "legal-records"),

    "legal-compliance/coppa": ("marketing_legal_coppa", "legal-consent"),

    "legal-compliance/gdpr": ("marketing_legal_gdpr", "privacy-dashboard"),

    "legal-compliance/wcag": ("marketing_legal_wcag", "a11y-matrix"),

    "legal-compliance/terms": ("marketing_legal_terms", "legal-document"),

    "legal-compliance/cookie-policy": ("marketing_legal_cookie", "cookie-matrix"),

}





class PersonalityRegistryDistinctionTest(SimpleTestCase):

    def test_all_personalities_have_unique_accent_viz_signature(self):

        seen: dict[str, str] = {}

        for pid in all_marketing_personality_ids():

            p = resolve_marketing_personality(pid)

            sig = personality_accent_signature(p)

            if sig in seen:

                self.fail(f"collision: {pid} and {seen[sig]} share {sig}")

            seen[sig] = pid



    def test_view_layer_slugs_resolve(self):

        for key in VIEW_LAYER_ROUTE_MAP:

            slug_key = key.replace("/", "-").replace("legal-compliance-", "legal-")

            if slug_key in VIEW_LAYER_SLUGS or key in VIEW_LAYER_SLUGS:

                continue

            mapped = key.replace("solutions/", "solutions-").replace("legal-compliance/", "legal-")

            p = resolve_marketing_personality(mapped)

            self.assertTrue(p["id"])



    def test_view_layer_page_definitions_registered(self):

        for slug in VIEW_LAYER_MARKETING_PAGE_SLUGS:

            self.assertIn(slug, MARKETING_PAGE_DEFINITIONS, msg=slug)



    def test_seeds_are_valid_json_and_have_series_or_timeline(self):

        for pid in all_marketing_personality_ids():

            seed = seed_for_personality(pid)

            parsed = json.loads(seed["json"])

            self.assertEqual(parsed["personality_id"], seed["personality_id"])

            self.assertTrue(parsed.get("metrics"))

            has_viz = bool(parsed.get("series")) or bool(parsed.get("timeline"))

            self.assertTrue(has_viz, msg=f"{pid} needs series or timeline")





class MarketingPersonalityRenderSmokeTest(unittest.TestCase):

    """Lightweight render checks via RequestFactory (avoids slow Client middleware)."""



    factory = RequestFactory()



    def _render_marketing_page(self, slug: str) -> str:

        path = f"/{slug}/"

        request = self.factory.get(path, HTTP_HOST="runmycampus.com")
        session = SessionStore()
        session.create()
        request.session = session

        with override_settings(ALLOWED_HOSTS=["*"], SECURE_SSL_REDIRECT=False):

            response = marketing_page(request, slug)

        self.assertEqual(response.status_code, 200, msg=slug)

        return response.content.decode("utf-8", errors="replace")



    def test_view_layer_pages_render_personality_viz(self):

        for slug in VIEW_LAYER_MARKETING_PAGE_SLUGS:

            html = self._render_marketing_page(slug)

            self.assertIn("data-mkt-personality-viz", html, msg=slug)

            self.assertIn(f'data-mkt-personality="{slug}"', html, msg=slug)

            p = resolve_marketing_personality(slug)

            self.assertIn(p["viz_engine"], html, msg=slug)



    def test_platform_page_has_distinct_personality_viz(self):

        html = self._render_marketing_page("platform")

        self.assertIn('data-mkt-personality="platform-hub"', html)

        self.assertIn("run-gauge", html)



    def test_pricing_page_has_pay_personality(self):

        html = self._render_marketing_page("pricing")

        self.assertIn('data-mkt-personality="pricing"', html)

        self.assertIn("pricing-matrix", html)



    def test_developers_page_has_api_playground_viz(self):

        html = self._render_marketing_page("developers")

        self.assertIn('data-mkt-personality="developers"', html)

        self.assertIn("api-playground", html)





class ViewLayerRouteResolveTest(SimpleTestCase):

    def test_all_view_layer_routes_reverse(self):

        for _key, (url_name, _viz) in VIEW_LAYER_ROUTE_MAP.items():

            try:

                reverse(url_name)

            except NoReverseMatch as exc:

                self.fail(f"cannot reverse {url_name}: {exc}")





class MarketingPersonalityAliasRouteTest(SimpleTestCase):

    """Redirect alias routes are registered (middleware may gate live GET in tests)."""

    def test_redirect_aliases_resolve_to_targets(self):
        cases = (
            ("marketing_portal_login", "global_login_discovery"),
            ("marketing_find_campus_portal", "find_school"),
            ("marketing_procurement_docs", "marketing_procurement_checklist"),
            ("marketing_implementation_timelines", "marketing_implementation_assurance"),
        )
        for start_name, end_name in cases:
            start_path = reverse(start_name)
            end_path = reverse(end_name)
            match = resolve(start_path)
            self.assertEqual(match.url_name, start_name)
            self.assertTrue(callable(match.func), msg=start_name)
            self.assertTrue(end_path.startswith("/"), msg=end_name)





class PersonalityContrastHeuristicTest(SimpleTestCase):

    """WCAG 2.2 AAA 7:1 heuristic on marketing cream + personality accent pairs."""



    _HEX_RE = re.compile(r"^#([0-9a-f]{6})$", re.I)



    def _luminance(self, hex_color: str) -> float:

        m = self._HEX_RE.match(hex_color.strip())

        self.assertIsNotNone(m)

        rgb = [int(m.group(1)[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]

        channels = []

        for c in rgb:

            channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)

        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]



    def _contrast(self, fg: str, bg: str) -> float:

        l1, l2 = self._luminance(fg), self._luminance(bg)

        lighter, darker = max(l1, l2), min(l1, l2)

        return (lighter + 0.05) / (darker + 0.05)



    def test_accent_ink_on_cream_meets_7_to_1(self):

        cream = "#faf7f2"

        failures = []

        for pid in all_marketing_personality_ids():

            p = resolve_marketing_personality(pid)

            ink = p.get("accent_ink") or p["accent"]

            if not self._HEX_RE.match(ink):

                continue

            ratio = self._contrast(ink, cream)

            if ratio < 7.0:

                failures.append(f"{pid}: {ratio:.2f}:1 ({ink} on {cream})")

        if failures:

            self.fail("AAA 7:1 failures:\n" + "\n".join(failures[:12]))


