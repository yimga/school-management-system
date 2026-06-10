"""Phase 2 portal shell layout, chromatic, and navigation contract tests."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[3]


class Phase2PortalFluidLayoutTests(SimpleTestCase):
    def test_portal_base_sets_fluid_layout_for_tenant(self):
        html = (ROOT / "templates" / "portal_base.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-layout="fluid"', html)
        self.assertIn("request.public_host_kind != 'manager'", html)

    def test_portal_bridge_css_fluid_document_scroll(self):
        css = (ROOT / "static" / "css" / "portal-app-shell-bridge.css").read_text(
            encoding="utf-8"
        )
        self.assertIn('html[data-rmc-layout="fluid"][data-surface="tenant"]', css)
        self.assertIn("overflow-y: visible", css)
        self.assertIn("max-height: none", css)

    def test_portal_sidebar_landscape_trap_respects_fluid(self):
        css = (ROOT / "static" / "css" / "portal-base-shell.css").read_text(encoding="utf-8")
        self.assertIn('html:not([data-rmc-layout="fluid"]) .sidebar', css)


class Phase2PortalNavigationTests(SimpleTestCase):
    def test_user_dropdown_logout_marker(self):
        html = (ROOT / "templates" / "components" / "user_dropdown.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-rmc-nav-logout", html)
        self.assertIn("accounts:logout", html)

    def test_logout_url_resolves(self):
        url = reverse("accounts:logout")
        self.assertTrue(url.startswith("/"))


class Phase2ChromaticTests(SimpleTestCase):
    def test_unauthenticated_header_uses_semantic_surface(self):
        html = (ROOT / "templates" / "unfold" / "helpers" / "unauthenticated_header.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("bg-base-50", html)
        self.assertNotIn("bg-white border", html)
