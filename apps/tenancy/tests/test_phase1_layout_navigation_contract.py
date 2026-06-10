"""Phase 1 layout, chromatic, and navigation contract tests."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[3]


class Phase1LayoutShellContractTests(SimpleTestCase):
    def test_fluid_shell_css_present(self):
        css = (ROOT / "static" / "css" / "rmc-app-shell.css").read_text(encoding="utf-8")
        self.assertIn(".rmc-app-shell--fluid", css)
        self.assertIn("html:has(.rmc-app-shell--fluid)", css)
        self.assertIn("overflow-y: auto", css)

    def test_tenant_admin_base_uses_fluid_layout(self):
        html = (ROOT / "templates" / "admin" / "base.html").read_text(encoding="utf-8")
        self.assertIn("rmc-app-shell--fluid", html)
        self.assertIn('data-rmc-layout="fluid"', html)
        self.assertNotIn("bg-white dark:bg-base-900", html)

    def test_nav_sidebar_drops_max_h_screen_trap(self):
        html = (ROOT / "templates" / "admin" / "nav_sidebar.html").read_text(encoding="utf-8")
        self.assertNotIn("max-h-screen", html)

    def test_navigation_inner_drops_min_h_screen_trap(self):
        html = (ROOT / "templates" / "unfold" / "helpers" / "navigation.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("min-h-screen", html)
        self.assertIn("min-h-0", html)


class Phase1NavigationContractTests(SimpleTestCase):
    def test_account_links_include_logout(self):
        html = (ROOT / "templates" / "unfold" / "helpers" / "account_links.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("accounts:logout", html)
        self.assertIn("data-rmc-nav-logout", html)

    def test_navigation_user_menu_opens_above_card(self):
        html = (ROOT / "templates" / "unfold" / "helpers" / "navigation_user.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("bottom-full", html)
        self.assertIn("overflow-visible", html)
        self.assertIn("z-[60]", html)
        self.assertIn("account_links.html", html)

    def test_logout_url_resolves(self):
        url = reverse("accounts:logout")
        self.assertTrue(url.startswith("/"))


class Phase1DeadHrefRepairTests(SimpleTestCase):
    def test_tenant_minimal_shell_has_no_href_hash_brand(self):
        html = (ROOT / "templates" / "schools" / "tenant_minimal_shell.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('href="#"', html)

    def test_group_detail_leave_uses_button_not_dead_href(self):
        html = (ROOT / "templates" / "communication" / "group_detail.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('href="#"', html)
        self.assertIn('data-confirm-href', html)

    def test_product_templates_href_hash_count_at_most_allowlisted(self):
        """Phase 1 target: no unmarked href=\"#\" in schools/communication templates."""
        offenders = []
        for rel in (
            "templates/schools/tenant_minimal_shell.html",
            "templates/communication/group_detail.html",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            if re.search(r'href\s*=\s*["\']#["\']', text):
                offenders.append(rel)
        self.assertEqual(offenders, [])


class Phase1ChromaticContractTests(SimpleTestCase):
    def test_admin_user_dropdown_uses_semantic_surfaces(self):
        html = (ROOT / "templates" / "unfold" / "helpers" / "navigation_user.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("bg-base-50", html)
        self.assertIn("dark:bg-base-900", html)
        self.assertNotIn("bg-white border", html)

    def test_admin_sidebar_user_menu_css_tokens(self):
        css = (ROOT / "static" / "css" / "admin-sidebar-backend-inspired.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".admin-sidebar-user-menu", css)
        self.assertIn("overflow: visible", css)
