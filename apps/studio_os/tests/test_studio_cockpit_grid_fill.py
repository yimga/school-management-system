"""Seal: Studio cockpit card-hub grids use auto-FIT, not auto-fill.

The recurring "studio things are just left-oriented / pages too long" complaint
is the CSS-grid `auto-fill` trap: `repeat(auto-fill, minmax(N, 1fr))` reserves
empty PHANTOM trailing tracks when a row has fewer cards than would fit, so the
cards cluster against the left edge with a wasted empty column on the right.
`auto-fit` collapses those empty tracks, letting the surviving cards stretch
(via the `1fr`) to fill the canvas width — the balanced layout the user wants.

This seals the two Studio COCKPIT CARD-HUB grids converted in the deliberate
layout pass (overview mode cards + output tiles) plus the already-converted
system-config hub, and — crucially — documents that the FIXED-TILE galleries
(brand-token swatches, gradient-stop chips) deliberately KEEP `auto-fill`: a lone
swatch stretched to full width would look broken. That distinction is why this
was a reviewed pass and not a blind find-replace, and this test guards against a
future blind sweep flipping the galleries too.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

_CSS_DIR = Path(__file__).resolve().parents[3] / "static" / "css"
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _rule_body(css: str, selector: str, *, occurrence: int = 0) -> str:
    """Return the nth `selector {...}` declaration block with CSS comments
    stripped — the prose comments deliberately mention "auto-fill", so the
    assertions must inspect the real declarations, not the explanation."""
    needle = selector + " {"
    start = -1
    for _ in range(occurrence + 1):
        start = css.find(needle, start + 1)
        assert start != -1, f"selector {selector!r} (occurrence {occurrence}) not found"
    open_brace = css.find("{", start)
    close_brace = css.find("}", open_brace)
    return _COMMENT.sub("", css[open_brace + 1 : close_brace])


class StudioCockpitGridFillTest(SimpleTestCase):
    def _read(self, name: str) -> str:
        return (_CSS_DIR / name).read_text(encoding="utf-8")

    def test_overview_mode_grid_is_auto_fit_both_breakpoints(self):
        css = self._read("studio-overview-cockpit.css")
        # base rule + the max-width:1366px responsive override
        for occ in (0, 1):
            body = _rule_body(css, ".rmc-overview-mode-grid", occurrence=occ)
            self.assertIn("auto-fit", body)
            self.assertNotIn("auto-fill", body)

    def test_output_tiles_is_auto_fit_both_breakpoints(self):
        css = self._read("studio-output-cockpit.css")
        for occ in (0, 1):
            body = _rule_body(css, ".rmc-output-tiles", occurrence=occ)
            self.assertIn("auto-fit", body)
            self.assertNotIn("auto-fill", body)

    def test_sysconf_hub_is_auto_fit(self):
        css = self._read("studio-system-config-console.css")
        body = _rule_body(css, ".sysconf-grid")
        self.assertIn("auto-fit", body)
        self.assertNotIn("auto-fill", body)

    def test_fixed_tile_galleries_keep_auto_fill_by_design(self):
        # These are fixed-size tile galleries, NOT card hubs: a lone tile must
        # keep its intrinsic width, not stretch to fill. A blind auto-fill ->
        # auto-fit sweep would wrongly flip them; this asserts the distinction.
        swatches = _rule_body(
            self._read("studio-output-cockpit.css"), ".rmc-output-brand-swatches"
        )
        self.assertIn("auto-fill", swatches)

        stops = _rule_body(self._read("tenant-studio-day1.css"), ".rmc-day1-stops")
        self.assertIn("auto-fill", stops)
