"""Seal: platform card-hub grids use auto-FIT, not auto-fill (non-studio passes).

Companion to test_studio_cockpit_grid_fill.py. The recurring "everything is
left-oriented / pages too long" complaint is the CSS-grid `auto-fill` trap:
`repeat(auto-fill, minmax(N, 1fr))` reserves empty PHANTOM trailing tracks when
a row has fewer cards than fit, so the cards cluster against the left edge with
a wasted empty column on the right. `auto-fit` collapses those empty tracks so
the surviving cards stretch (via the `1fr`) to fill the canvas width.

This is the deliberate follow-up sweep of the ~45 auto-fill grids, taken one
scoped surface family at a time (NOT a blind find-replace — fixed-tile
galleries legitimately keep auto-fill). Grids sealed here are added family by
family as each pass ships.

  WIZARD family (tenant-facing setup / onboarding flows):
    .rmc-wz-grid, .rmc-wizard-index-grid, .rmc-wizard-zf-domain-grid, .ovendor-grid
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

_CSS_DIR = Path(__file__).resolve().parents[3] / "static" / "css"
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _rule_body(css: str, selector: str, *, occurrence: int = 0) -> str:
    """Return the nth `selector {...}` block with CSS comments stripped — the
    prose comments deliberately say "auto-fill", so assertions must inspect the
    real declarations, not the explanation."""
    needle = selector + " {"
    start = -1
    for _ in range(occurrence + 1):
        start = css.find(needle, start + 1)
        assert start != -1, f"selector {selector!r} (occurrence {occurrence}) not found"
    open_brace = css.find("{", start)
    close_brace = css.find("}", open_brace)
    return _COMMENT.sub("", css[open_brace + 1 : close_brace])


class WizardCardHubGridFillTest(SimpleTestCase):
    def _read(self, name: str) -> str:
        return (_CSS_DIR / name).read_text(encoding="utf-8")

    def _assert_auto_fit(self, css: str, selector: str, *, occurrence: int = 0):
        body = _rule_body(css, selector, occurrence=occurrence)
        self.assertIn("auto-fit", body, f"{selector} (occ {occurrence}) must be auto-fit")
        self.assertNotIn("auto-fill", body, f"{selector} (occ {occurrence}) still auto-fill")

    def test_wizard_engine_card_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("rmc-wizard-engine.css"), ".rmc-wz-grid")

    def test_wizard_index_card_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("rmc-wizard-index.css"), ".rmc-wizard-index-grid")

    def test_wizard_zf_domain_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("rmc-wizard.css"), ".rmc-wizard-zf-domain-grid")

    def test_onboarding_vendor_grid_is_auto_fit_below_desktop(self):
        css = self._read("onboarding-migration.css")
        # base + the >=576px override are the auto-fill sites we converted.
        self._assert_auto_fit(css, ".ovendor-grid", occurrence=0)
        self._assert_auto_fit(css, ".ovendor-grid", occurrence=1)

    def test_onboarding_vendor_grid_keeps_deliberate_4col_on_desktop(self):
        # The >=992px rule is a deliberate fixed 4-column cap (vendor tiles are a
        # small known set), NOT the auto-fill trap. Guard that the sweep did not
        # accidentally rewrite it.
        css = self._read("onboarding-migration.css")
        body = _rule_body(css, ".ovendor-grid", occurrence=2)
        self.assertIn("repeat(4,", body)
