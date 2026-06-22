"""Platform chrome-strip density pass contract (Option B, 2026-06-22).

The shell-level Flow Thread bar + flow launchpad stack above content on every
authenticated page. A density override in rmc-class-grammar-ext.css tightens
their vertical rhythm platform-wide. Because it OVERRIDES the base rules in
rmc-class-grammar.css via the cascade, the extension file MUST load after the
grammar file on every strip-hosting shell — these checks lock both the override
and that load order.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]
EXT_CSS = REPO_ROOT / "static" / "css" / "rmc-class-grammar-ext.css"
TEMPLATES = REPO_ROOT / "templates"
STRIP_SHELLS = [
    "base.html",
    "portal_base.html",
    "control_plane_skeleton.html",
    "admin/base_site.html",
]


class ChromeStripDensityTests(SimpleTestCase):
    def test_density_override_present(self) -> None:
        css = EXT_CSS.read_text(encoding="utf-8")
        # the inline-label compaction + tightened strip rhythm
        self.assertIn("chrome-strip density pass", css)
        self.assertIn(".rmc-flow-launchpad__lead", css)
        # the launchpad becomes a flex row so the label folds inline
        block = css.split("chrome-strip density pass", 1)[1]
        self.assertIn("display: flex", block)
        self.assertIn(".rmc-page-explain-strip", block)

    def test_ext_loads_after_grammar_on_every_strip_shell(self) -> None:
        """The override only wins if -ext.css is linked AFTER -grammar.css."""
        for shell in STRIP_SHELLS:
            src = (TEMPLATES / shell).read_text(encoding="utf-8")
            with self.subTest(shell=shell):
                grammar = src.find("css/rmc-class-grammar.css")
                ext = src.find("css/rmc-class-grammar-ext.css")
                self.assertNotEqual(grammar, -1, f"{shell}: grammar.css not linked")
                self.assertNotEqual(ext, -1, f"{shell}: grammar-ext.css not linked")
                self.assertLess(
                    grammar, ext,
                    f"{shell}: rmc-class-grammar-ext.css must load AFTER "
                    f"rmc-class-grammar.css or the density override won't apply.",
                )
