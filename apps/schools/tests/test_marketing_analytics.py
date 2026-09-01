"""Marketing analytics contract — privacy-safe payloads and shell wiring."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

REPO = Path(__file__).resolve().parents[3]
ANALYTICS_JS = REPO / "static" / "marketing" / "js" / "marketing-analytics.js"
HEADER = REPO / "templates" / "marketing" / "marketing_header.html"
LANDING = REPO / "templates" / "schools" / "marketing_landing_v2.html"
PRICING = REPO / "templates" / "marketing" / "pages" / "type_pricing.html"
BASE_MARKETING = REPO / "templates" / "marketing" / "base_marketing.html"

PII_KEYS = ("email", "phone", "password", "school_name", "message", "csrf")


class MarketingAnalyticsTests(SimpleTestCase):
    def test_analytics_js_allowlist_has_no_pii_keys(self) -> None:
        text = ANALYTICS_JS.read_text(encoding="utf-8")
        for key in PII_KEYS:
            self.assertNotIn(f"{key}:", text, f"PII key {key} must not appear in analytics allowlist")

    def test_header_nav_links_carry_menu_analytics_attributes(self) -> None:
        # All three are plain markup, and this test was the whole read: a source
        # check passes over a header whose body is inside {% comment %}, on which
        # marketing-analytics.js would see no menu links at all. Ask the engine.
        assert_markup(
            self, HEADER, "data-menu-name=", "data-menu-link=", 'data-cta="demo"'
        )

    def test_home_ctas_carry_cta_analytics_attributes(self) -> None:
        home_story = REPO / "templates" / "marketing" / "components" / "_home_os_story.html"
        text = LANDING.read_text(encoding="utf-8") + home_story.read_text(encoding="utf-8")
        self.assertGreaterEqual(len(re.findall(r'data-cta="[^"]+"', text)), 3)
        self.assertIn("data-page=", text)

    def test_marketing_analytics_script_wired_in_shell(self) -> None:
        partial = REPO / "templates" / "marketing" / "partials" / "marketing_analytics.html"
        body = partial.read_text(encoding="utf-8")
        # The bundle name is a {% static %} argument, never emitted text.
        self.assertIn("marketing-analytics.js", body)
        # "Wired in shell" is a wiring claim, so ask the engine: a {% comment %}
        # keeps the filename in base_marketing's bytes and builds no IncludeNode,
        # which is precisely the shell that ships no analytics.
        assert_wires(self, BASE_MARKETING, "marketing_analytics.html")

    def test_pricing_ctas_track_plan_interest_without_pii(self) -> None:
        text = PRICING.read_text(encoding="utf-8")
        # This attribute carries a {{ plan.plan }} variable, so it is split across
        # a TextNode and a VariableNode and no parse can see it whole.
        self.assertIn('data-plan-name="{{ plan.plan }}"', text)
        analytics = ANALYTICS_JS.read_text(encoding="utf-8")
        self.assertIn("pricing_plan_interest", analytics)
        self.assertIn("plan_name", analytics)
        # The CTA marker is literal, and it is the hook the analytics bundle
        # binds to -- so assert the pricing page really EMITS it.
        assert_markup(self, PRICING, 'data-cta="pricing"')
