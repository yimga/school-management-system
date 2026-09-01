"""Phase 2 portal shell layout, chromatic, and navigation contract tests."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[3]


class Phase2PortalFluidLayoutTests(SimpleTestCase):
    # test_portal_base_sets_fluid_layout_for_tenant measured VACUOUS, and its
    # second assertion was the tell: it looked for the GUARD EXPRESSION in the
    # source, which is present whichever branch renders -- so it could not tell
    # a tenant host from an operator one, which is the only thing it was for.
    # Now PortalFluidLayoutRendersTests below, which renders both hosts.

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


# Phase2ChromaticTests read the partial as TEXT and looked for the utility
# class "bg-base-50". That class was deliberately retired on 2026-08-09
# (56ad1757a) in favour of .rmc-theme-surface, which is the STRONGER
# contract: it paints from --rmc-safe-surface and swaps in dark mode through
# a variable instead of a second utility. Nobody updated the test, so it has
# been RED ever since -- asserting a token the product had replaced with a
# better one. It is now Phase2ChromaticSurfaceRendersTests at the bottom.


# --------------------------------------------------------------------------
# Rendered-output replacements (2026-09-01).
#
# scripts/verify_test_asserts_behaviour.py measured the source checks these
# replace as VACUOUS: each still passed with the template it named made to
# render nothing, while every string it asserts stayed in the file's bytes.
#
# They are TestCase, not SimpleTestCase, and that is not an oversight. The
# shells query the database while rendering (a context processor does), so a
# SimpleTestCase raises DatabaseOperationForbidden -- measured, not assumed.
# The consequence is deliberate and worth knowing: the harness only measures
# DB-free tests, so a test fixed this way leaves its scope rather than
# flipping to SOUND inside it.
# --------------------------------------------------------------------------

from django.test import TestCase  # noqa: E402

from apps.siteconfig.tests._shell_render import (  # noqa: E402
    BASE_URLCONF,
    MANAGER_URLCONF,
    TENANT_URLCONF,
    render_shell,
)


class PortalFluidLayoutRendersTests(TestCase):
    def test_the_tenant_host_gets_the_fluid_layout(self):
        self.assertIn(
            'data-rmc-layout="fluid"',
            render_shell("portal_base.html", urlconf=TENANT_URLCONF, host_kind="tenant"),
        )

    def test_the_operator_host_does_not(self):
        """The mirror, which a substring check on the source cannot express."""
        self.assertNotIn(
            'data-rmc-layout="fluid"',
            render_shell(
                "portal_base.html", urlconf=MANAGER_URLCONF, host_kind="manager"
            ),
        )


class Phase2ChromaticSurfaceRendersTests(TestCase):
    """The unauthenticated header must take its surface from a THEME TOKEN.

    Swapping the old needle for the new class name would reproduce exactly the
    defect this audit keeps finding: a class in a template proves nothing if
    the stylesheet that gives it a background has been deleted. So this asserts
    BOTH halves -- the rendered element carries the class, and the shipped rule
    still paints a background for it -- and reads OUTPUT, not source.

    TestCase, not SimpleTestCase, and that was measured the hard way: a bare
    render of this partial outside a test succeeds, so it LOOKS DB-free, but
    under SimpleTestCase it raises DatabaseOperationForbidden -- the
    siteconfig context processor reads the active theme while rendering.
    """

    _PARTIAL = "unfold/helpers/unauthenticated_header.html"
    _SURFACE_CSS = ROOT / "static" / "css" / "rmc-theme-surface-safety-v1.css"

    def _render(self):
        return render_shell(self._PARTIAL, urlconf=BASE_URLCONF, host_kind="base")

    def test_the_served_header_carries_the_semantic_surface(self):
        self.assertIn("rmc-theme-surface", self._render())

    def test_the_served_header_hardcodes_no_opaque_background(self):
        """The point of the token: no utility that ignores the active theme."""
        html = self._render()
        for utility in ("bg-white", "bg-base-50", "bg-base-800"):
            with self.subTest(utility=utility):
                self.assertNotIn(utility, html)

    def test_the_semantic_surface_is_actually_painted(self):
        """The half a class-name check cannot see: does the RULE still exist?"""
        css = self._SURFACE_CSS.read_text(encoding="utf-8")
        blocks = [
            body
            for selectors, body in (
                (chunk.split("{", 1) + [""])[:2]
                for chunk in css.split("}")
                if "{" in chunk
            )
            if ".rmc-theme-surface," in selectors + ","
            or ".rmc-theme-surface{" in selectors.replace(" ", "") + "{"
        ]
        self.assertTrue(
            blocks, ".rmc-theme-surface has no rule in rmc-theme-surface-safety-v1.css"
        )
        self.assertTrue(
            any("background" in body for body in blocks),
            ".rmc-theme-surface is selected but nothing paints its background",
        )
