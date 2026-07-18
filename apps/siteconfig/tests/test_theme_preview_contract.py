"""Contract tests for theme preview proof-of-render + publish guard audit."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[3]


class ThemePreviewContractTests(TestCase):
    def test_js_does_not_eagerly_set_preview_confirmed_on_click(self):
        js = (
            ROOT
            / "static/js/_pages/siteconfig__partials__theme_colors_page_body-1.js"
        ).read_text(encoding="utf-8")
        # Must not set confirmed before the preview opens.
        self.assertIn("Do NOT set preview_confirmed here", js)
        self.assertIn("openPreviewUrl", js)
        self.assertIn("showFallbackPanel", js)
        self.assertIn("trans_preview_popup_blocked", js)
        self.assertIn("setPreviewEvidence", js)
        self.assertIn("data-rmc-preview-rendered", js)
        # Success toast only after a successful open path exists.
        self.assertIn("var opened = openPreviewUrl(redirectUrl);", js)
        self.assertIn("if (opened && typeof window.showToast", js)

    def test_confirm_checkbox_starts_disabled(self):
        html = (
            ROOT / "templates/siteconfig/partials/theme_colors_page_body.html"
        ).read_text(encoding="utf-8")
        self.assertIn('id="theme-confirm-publish"', html)
        self.assertIn("disabled", html[html.index("theme-confirm-publish") - 80 :])
        self.assertIn("theme-preview-evidence-status", html)
        self.assertIn("data-rmc-preview-fallbacks", html)
        self.assertIn("theme-live-preview-modal", html)
        self.assertIn("rmc-live-preview-contract.css", html)

    def test_publish_guard_bypass_is_audit_logged(self):
        src = (ROOT / "apps/siteconfig/views.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("theme_publish_guard_bypassed"), 2)
        self.assertEqual(src.count('"guard_bypassed": bool(guard_bypassed)'), 2)

    def test_preview_loaded_bridge_exists(self):
        js = (ROOT / "static/js/rmc-theme-preview-loaded.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-preview-loaded", js)
        portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn("rmc-theme-preview-loaded.js", portal)

    def test_live_preview_button_partial_exists(self):
        path = ROOT / "templates/components/live_preview_button.html"
        self.assertTrue(path.is_file())
        self.assertIn("data-rmc-live-preview-trigger", path.read_text(encoding="utf-8"))
