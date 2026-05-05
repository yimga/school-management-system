from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class PremiumVisualSystemPolishTests(SimpleTestCase):
    def test_premium_polish_css_loads_in_public_and_authenticated_shells(self):
        shell_paths = [
            ROOT / "templates" / "marketing" / "base_marketing.html",
            ROOT / "templates" / "base.html",
            ROOT / "templates" / "portal_base.html",
            ROOT / "templates" / "control_plane_base.html",
        ]

        for path in shell_paths:
            with self.subTest(path=path.name):
                html = path.read_text(encoding="utf-8")
                self.assertIn("css/rmc-premium-polish.css", html)
                self.assertRegex(html, r"data-rmc-(?:premium|os)-shell")

    def test_premium_css_keeps_fonts_safe_and_token_driven(self):
        inter = (ROOT / "static" / "css" / "vendor" / "inter.css").read_text(
            encoding="utf-8"
        )
        polish = (ROOT / "static" / "css" / "rmc-premium-polish.css").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("@font-face", inter)
        self.assertNotIn(".woff2", inter)
        self.assertIn("var(--rmc-premium", polish)
        self.assertIn("--rmc-polish-radius", polish)

    def test_active_shells_do_not_introduce_dummy_actions(self):
        shell_paths = [
            ROOT / "templates" / "marketing" / "base_marketing.html",
            ROOT / "templates" / "base.html",
            ROOT / "templates" / "portal_base.html",
            ROOT / "templates" / "control_plane_base.html",
        ]
        dummy_pattern = re.compile(r'(?:href|action)=["\']#["\']')

        for path in shell_paths:
            with self.subTest(path=path.name):
                html = path.read_text(encoding="utf-8")
                self.assertIsNone(dummy_pattern.search(html))

    def test_payment_external_honesty_language_remains_available(self):
        payment_template = (
            ROOT / "templates" / "finance" / "payment_readiness_dashboard.html"
        ).read_text(encoding="utf-8")
        self.assertIn("external_required", payment_template)
        self.assertIn("missing credentials", payment_template.lower())
        self.assertIn("manual fallback", payment_template.lower())
