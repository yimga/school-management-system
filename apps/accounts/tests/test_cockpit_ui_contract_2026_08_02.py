"""Must-fire UI contract for the 2026-08-02 Admin Home "command cockpit" consolidation.

These guard the shipped, approved fixes so they cannot silently regress. They are
deliberately *must-fire* (assert the fixed state is present), because a negative
test can never detect a reverted CSS/template fix.

All read source files or render a shared partial directly (SimpleTestCase, no DB),
so they run under any harness without the 20-minute test-database build.

Shipped fixes covered:
  1. The activation-checklist CTA is a real button (background + border + padding),
     not the old bare inline-block text link (``.rmc-setup-surface__all``).
  2. The Phase-8 "dashboard intent" (ROLE_HOME / JTBD) strip is retired from the
     visible surface via ``.visually-hidden`` while keeping the coverage/density
     contract tokens — one shared component, ~90 dashboards.
  3. The mission-season hint uses accessible ink (never Bootstrap ``.text-muted``
     on the pale-cream mission band, which measured ~1.4:1 — a WCAG fail).
"""

from __future__ import annotations

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase

# apps/accounts/tests/<this file>  ->  parents[3] == repository root
ROOT = Path(__file__).resolve().parents[3]


def _css_rule_body(css: str, selector_with_brace: str) -> str:
    """Return the declaration body of the first matching CSS rule."""
    assert selector_with_brace in css, f"selector not found: {selector_with_brace!r}"
    return css.split(selector_with_brace, 1)[1].split("}", 1)[0]


class ChecklistButtonContractTests(SimpleTestCase):
    def test_setup_surface_all_is_a_real_button(self) -> None:
        css = (ROOT / "static" / "css" / "rmc-setup-surface.css").read_text(encoding="utf-8")
        block = _css_rule_body(css, ".rmc-setup-surface__all {")
        for prop in ("background", "border", "padding", "border-radius"):
            self.assertIn(
                prop,
                block,
                f".rmc-setup-surface__all must set {prop!r} to read as a real button",
            )
        # must-fire: the old bare-link signature is gone
        self.assertNotIn(
            "display: inline-block;",
            block,
            ".rmc-setup-surface__all reverted to the bare inline-block text link",
        )
        self.assertIn("inline-flex", block)

    def test_partial_renders_checklist_button_with_icon(self) -> None:
        html = (
            ROOT / "templates" / "partials" / "tenant" / "setup_command_surface.html"
        ).read_text(encoding="utf-8")
        self.assertIn('class="rmc-setup-surface__all"', html)
        self.assertIn("bi-check2-square", html)  # affordance icon in the button


class Phase8IntentStripRetiredTests(SimpleTestCase):
    def _render(self, path: str) -> str:
        return Template(
            '{% load phase8_tags %}{% phase8_dashboard_declaration "' + path + '" %}'
        ).render(Context({}))

    def test_strip_is_visually_hidden_but_keeps_contract_tokens(self) -> None:
        for path in (
            "accounts/backend_dashboard.html",
            "schools/super_dashboard.html",
            "finance/dashboard.html",
        ):
            with self.subTest(path=path):
                html = self._render(path)
                # Coverage / density contract must survive (see
                # test_phase8_registry_full_coverage + dashboard_density_check).
                self.assertIn("phase8-declaration-strip", html)
                self.assertIn("data-phase8-declaration", html)
                # Retired from the visible surface.
                self.assertIn("visually-hidden", html)


class SeasonHintContrastTests(SimpleTestCase):
    SEASON_TEMPLATES = (
        "templates/accounts/backend_dashboard.html",
        "templates/schools/super_dashboard.html",
    )

    def test_season_hint_drops_text_muted(self) -> None:
        for rel in self.SEASON_TEMPLATES:
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                idx = text.find("rmc-page-masthead__season")
                self.assertNotEqual(idx, -1, f"{rel}: season band missing")
                window = text[idx : idx + 400]
                self.assertIn("rmc-page-masthead__season-hint", window, rel)
                # must-fire: the low-contrast muted span must not reappear on the band
                self.assertNotIn(
                    'class="text-muted"',
                    window,
                    f"{rel}: season hint reverted to .text-muted (WCAG fail on cream)",
                )

    def test_css_season_has_explicit_accessible_ink(self) -> None:
        css = (
            ROOT / "static" / "css" / "rmc-page-archetypes-max.css"
        ).read_text(encoding="utf-8")
        block = _css_rule_body(css, ".rmc-page-masthead__season {")
        self.assertIn("color:", block, ".rmc-page-masthead__season must set explicit ink")
        self.assertIn("--text-primary", block)


class AppearanceStripCollapseTests(SimpleTestCase):
    def test_style_strip_collapses_chips_behind_disclosure(self) -> None:
        text = (
            ROOT / "templates" / "partials" / "tenant" / "setup_dashboard_style_strip.html"
        ).read_text(encoding="utf-8")
        self.assertIn("rmc-setup-style-strip__disclosure", text)
        self.assertIn("<details", text)
        self.assertIn("<summary", text)
        # chips are still in the DOM (progressive, no-JS friendly, no data loss)
        self.assertIn("rmc-setup-style-strip__chip", text)

    def test_css_defines_the_disclosure(self) -> None:
        css = (ROOT / "static" / "css" / "rmc-setup-surface.css").read_text(encoding="utf-8")
        self.assertIn(".rmc-setup-style-strip__disclosure", css)
        self.assertIn(".rmc-setup-style-strip__summary", css)
