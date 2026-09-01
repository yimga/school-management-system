"""Owner-program audit fix (HOLE #3): --text-on-brand must reach the tenant shell.

Wave 3-tail-B computed an adaptive on-brand ink but only rendered it on
base.html; the tenant shell (portal_base.html) never emitted it, so headers stayed
washed out on light brands. The `text_on_brand` filter + a `--text-on-brand`
emission in portal_base.html's own :root close that. These tests assert both the
filter logic AND that the shell actually wires it (regression guard).
"""

from __future__ import annotations

import pathlib

from django.template.loader import get_template
from django.test import SimpleTestCase

from apps.siteconfig.templatetags.control_console import text_on_brand
from apps.siteconfig.tests._template_nodes import assert_markup


class TextOnBrandFilterTests(SimpleTestCase):
    def test_light_brand_gets_dark_ink(self):
        self.assertEqual(text_on_brand("#facc15"), "#0f172a")

    def test_dark_brand_gets_light_ink(self):
        self.assertEqual(text_on_brand("#4f46e5"), "#f1f5f9")

    def test_bad_input_never_raises(self):
        # returns a valid color, never an exception
        self.assertTrue(str(text_on_brand(None)).startswith("#"))

    def test_portal_shell_emits_adaptive_text_on_brand(self):
        # the tenant shell must render --text-on-brand through the filter, not a
        # static #fff -- this is the exact hole the audit caught.
        root = pathlib.Path(__file__).resolve().parents[3]
        portal_base = root / "templates" / "portal_base.html"
        src = portal_base.read_text(encoding="utf-8")
        # Both of these straddle a {{ }} expression, so each is split across a
        # TextNode and a VariableNode and no parse can see either whole: they stay
        # source reads, and they are what pins the FILTER rather than a literal.
        self.assertIn("--text-on-brand: {{ theme.primary_color", src)
        self.assertIn("|text_on_brand }};", src)
        # The custom property itself is emitted text, and "emits" is the claim in
        # this test's own name -- a {% comment %} keeps both strings above in the
        # bytes and puts no --text-on-brand on the page.
        assert_markup(self, portal_base, "--text-on-brand")

    def test_portal_shell_compiles_with_filter(self):
        get_template("portal_base.html")  # must not raise (filter is loaded)
