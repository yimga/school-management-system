"""Marketing analytics contract — privacy-safe payloads and shell wiring."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]
ANALYTICS_JS = REPO / "static" / "marketing" / "js" / "marketing-analytics.js"
HEADER = REPO / "templates" / "marketing" / "marketing_header.html"
LANDING = REPO / "templates" / "schools" / "marketing_landing_v2.html"

PII_KEYS = ("email", "phone", "password", "school_name", "message", "csrf")


class MarketingAnalyticsTests(SimpleTestCase):
    def test_analytics_js_allowlist_has_no_pii_keys(self) -> None:
        text = ANALYTICS_JS.read_text(encoding="utf-8")
        for key in PII_KEYS:
            self.assertNotIn(f"{key}:", text, f"PII key {key} must not appear in analytics allowlist")

    def test_header_nav_links_carry_menu_analytics_attributes(self) -> None:
        text = HEADER.read_text(encoding="utf-8")
        self.assertIn("data-menu-name=", text)
        self.assertIn("data-menu-link=", text)
        self.assertIn('data-cta="demo"', text)

    def test_home_ctas_carry_cta_analytics_attributes(self) -> None:
        home_story = REPO / "templates" / "marketing" / "components" / "_home_os_story.html"
        text = LANDING.read_text(encoding="utf-8") + home_story.read_text(encoding="utf-8")
        self.assertGreaterEqual(len(re.findall(r'data-cta="[^"]+"', text)), 3)
        self.assertIn("data-page=", text)

    def test_marketing_analytics_script_wired_in_shell(self) -> None:
        partial = REPO / "templates" / "marketing" / "partials" / "marketing_analytics.html"
        body = partial.read_text(encoding="utf-8")
        self.assertIn("marketing-analytics.js", body)
        base = REPO / "templates" / "marketing" / "base_marketing.html"
        self.assertIn("marketing_analytics.html", base.read_text(encoding="utf-8"))
