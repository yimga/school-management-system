"""Phase 1 layout, chromatic, and navigation contract tests."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from apps.siteconfig.tests._template_nodes import (
    assert_does_not_emit,
    assert_markup,
    assert_wires,
)

ROOT = Path(__file__).resolve().parents[3]

NAVIGATION = ROOT / "templates" / "unfold" / "helpers" / "navigation.html"
NAVIGATION_USER = ROOT / "templates" / "unfold" / "helpers" / "navigation_user.html"
ADMIN_BASE = ROOT / "templates" / "admin" / "base.html"
ACCOUNT_LINKS = ROOT / "templates" / "unfold" / "helpers" / "account_links.html"
GROUP_DETAIL = ROOT / "templates" / "communication" / "group_detail.html"


class Phase1LayoutShellContractTests(SimpleTestCase):
    def test_fluid_shell_css_present(self):
        css = (ROOT / "static" / "css" / "rmc-app-shell.css").read_text(encoding="utf-8")
        self.assertIn(".rmc-app-shell--fluid", css)
        self.assertIn("html:has(.rmc-app-shell--fluid)", css)
        self.assertIn("overflow-y: auto", css)

    def test_tenant_admin_base_is_the_two_col_grid_and_never_fluid(self):
        # RENAMED, because the contract reversed and the old name asserted the
        # opposite of what admin/base.html now documents in its own comment:
        #   "Tenant admin uses the same 2-col grid + canvas scroll as manager --
        #    never rmc-app-shell--fluid (that stacks sidebar over canvas and
        #    locks scroll)."
        #
        # The old assertIn("rmc-app-shell--fluid") PASSED -- on that comment.
        # The string is in the file exactly once and the page never emits it,
        # so a source read could not tell a class from a prohibition on it.
        # It went red only on data-rmc-layout="fluid", which is simply gone.
        assert_markup(
            self,
            ADMIN_BASE,
            "rmc-app-shell",
            "admin-cp-unified-page",
            'data-rmc-shell-root="django-admin"',
        )
        assert_does_not_emit(
            self,
            ADMIN_BASE,
            "rmc-app-shell--fluid",
            "bg-white dark:bg-base-900",
        )

    def test_nav_sidebar_drops_max_h_screen_trap(self):
        html = (ROOT / "templates" / "admin" / "nav_sidebar.html").read_text(encoding="utf-8")
        self.assertNotIn("max-h-screen", html)

    def test_navigation_inner_drops_min_h_screen_trap(self):
        html = NAVIGATION.read_text(encoding="utf-8")
        # An absence is only meaningful over bytes, so the assertNotIn stays as a
        # read. The replacement class has to be on the ELEMENT, though, and a
        # class parked inside {% comment %} scrolls nothing -- ask the engine.
        self.assertNotIn("min-h-screen", html)
        self.assertIn("min-h-0", html)
        assert_markup(self, NAVIGATION, "min-h-0")


class Phase1NavigationContractTests(SimpleTestCase):
    def test_account_links_include_logout(self):
        html = ACCOUNT_LINKS.read_text(encoding="utf-8")
        # "accounts:logout" is a {% url %} argument -- template code, which no
        # parse and no render can see, so that one stays a source read. The hook
        # the nav JS binds to is markup, and markup is the engine's question.
        self.assertIn("accounts:logout", html)
        self.assertIn("data-rmc-nav-logout", html)
        assert_markup(self, ACCOUNT_LINKS, "data-rmc-nav-logout")

    def test_navigation_user_menu_opens_above_card(self):
        # Three utility classes and an include: every one of them is something
        # the template must actually DO, and reading the bytes could not tell a
        # live class from one sitting in a comment. So none of it is a read now.
        assert_markup(
            self,
            NAVIGATION_USER,
            "bottom-full",
            "overflow-visible",
            "z-[60]",
        )
        assert_wires(self, NAVIGATION_USER, "unfold/helpers/account_links.html")

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
        html = GROUP_DETAIL.read_text(encoding="utf-8")
        # The absence of href="#" is a byte question and stays one. What replaced
        # it is not: a real <button> carrying the leave URL, plus the confirm
        # modal it targets. Both asked of the engine, so a commented-out repair
        # cannot pass for a repair.
        self.assertNotIn('href="#"', html)
        self.assertIn('data-confirm-href', html)
        assert_markup(
            self,
            GROUP_DETAIL,
            "data-confirm-href",
            'data-bs-target="#leaveGroupConfirm"',
        )
        assert_wires(self, GROUP_DETAIL, "components/confirm_modal.html")

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
        # Went red when the dropdown moved off the raw Tailwind pair
        # (bg-base-50 / dark:bg-base-900) onto the project's own
        # rmc-theme-surface, which is the same intent expressed once instead
        # of twice. The claim -- semantic surface tokens, never a hardcoded
        # white -- is unchanged; only the tokens moved.
        assert_markup(
            self,
            NAVIGATION_USER,
            "rmc-theme-surface",
            "border-base-200",
            "dark:border-base-800",
        )
        assert_does_not_emit(
            self, NAVIGATION_USER, "bg-white"
        )

    def test_admin_sidebar_user_menu_css_tokens(self):
        css = (ROOT / "static" / "css" / "admin-sidebar-backend-inspired.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".admin-sidebar-user-menu", css)
        self.assertIn("overflow: visible", css)
