"""Unit tests for the theme hue-coherence gate.

Stdlib only, like its sibling scanner tests — the gate runs in the deps-free boundary
job, so its tests must too.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "scripts" / "scan_theme_hue_coherence.py"


def _load():
    spec = importlib.util.spec_from_file_location("_theme_hue_gate", SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()


def scan(css: str):
    return gate.scan_text("static/css/probe.css", css)


def block(**decls) -> str:
    body = "\n".join(f"  {k.replace('_', '-')}: {v};" for k, v in decls.items())
    return "body.portal-backend-probe {\n" + body + "\n}"


class ItCatchesTheDefectItWasBuiltForTests(unittest.TestCase):
    """The exact shape that shipped: a navy ground over a borrowed warm ramp."""

    def test_navy_ground_with_brown_surfaces_is_a_finding(self):
        css = block(
            background="#030712",
            **{"--backend-surface": "#1a1612", "--backend-surface-alt": "#241e18"},
        )
        findings = scan(css)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["theme"], "probe")
        self.assertGreater(findings[0]["spread_degrees"], 150)

    def test_the_shipped_ink_values_are_a_finding(self):
        """Pinned to the literal values, so a revert cannot pass quietly."""
        css = block(
            background="#030712",
            color="#fffaf0",
            **{
                "--backend-text": "#fffaf0",
                "--backend-text-muted": "#a8a092",
                "--backend-surface": "#1a1612",
                "--backend-surface-alt": "#241e18",
            },
        )
        self.assertEqual(len(scan(css)), 1)

    def test_the_replacement_ink_values_are_clean(self):
        css = block(
            background="#030712",
            **{
                "--backend-text": "#f8fafc",
                "--backend-text-muted": "#94a3b8",
                "--backend-surface": "#0f172a",
                "--backend-surface-alt": "#1e293b",
            },
        )
        self.assertEqual(scan(css), [])

    def test_a_single_warm_stop_in_a_cool_gradient_is_caught(self):
        """Snow's canvas ran sky-blue to floral white; only the last stop was wrong."""
        css = block(
            background="linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #fffaf0 100%)",
            **{"--backend-surface": "#ffffff", "--backend-surface-alt": "#f0f9ff"},
        )
        self.assertEqual(len(scan(css)), 1)

    def test_one_wrong_token_among_right_ones_is_caught(self):
        """Indigo was coherent everywhere except its muted text, which was amber."""
        css = block(
            background="#1e1b4b",
            **{
                "--backend-text": "#e0e7ff",
                "--backend-text-muted": "#e6a052",
                "--backend-surface": "#312e81",
                "--backend-surface-alt": "#3730a3",
            },
        )
        self.assertEqual(len(scan(css)), 1)


class ItDoesNotCryWolfTests(unittest.TestCase):
    """Every one of these is a real theme shape that must stay green."""

    def test_all_neutral_theme_is_coherent(self):
        css = block(
            background="#000000",
            **{"--backend-surface": "#171717", "--backend-surface-alt": "#262626"},
        )
        self.assertEqual(scan(css), [])

    def test_warm_on_warm_is_coherent(self):
        css = block(
            background="#241e18",
            **{"--backend-surface": "#2c241d", "--backend-surface-alt": "#544d44"},
        )
        self.assertEqual(scan(css), [])

    def test_green_theme_is_not_mistaken_for_a_mix(self):
        """A red/blue split would misread green as 'cool'; hue angle does not."""
        css = block(
            background="#0d1f12",
            **{"--backend-surface": "#14532d", "--backend-surface-alt": "#166534"},
        )
        self.assertEqual(scan(css), [])

    def test_a_ramp_may_drift_as_it_lightens(self):
        css = block(
            background="#0c1929",
            **{"--backend-surface": "#0e3a5f", "--backend-surface-alt": "#164e63"},
        )
        self.assertEqual(scan(css), [])

    def test_near_grey_values_have_no_hue_to_disagree_with(self):
        """#18181b and #f8fafc are greys; neither should anchor a spread."""
        css = block(
            background="#18181b",
            **{
                "--backend-text": "#f8fafc",
                "--backend-surface": "#27272a",
                "--backend-surface-alt": "#3f3f46",
            },
        )
        self.assertEqual(scan(css), [])

    def test_a_rule_scoped_to_a_theme_is_not_a_theme_definition(self):
        css = (
            "body.portal-backend-ink .card { background: #241e18; color: #030712; }"
        )
        self.assertEqual(scan(css), [])

    def test_a_block_with_one_colour_cannot_disagree(self):
        css = block(background="#030712", **{"--backend-surface": "var(--x)"})
        self.assertEqual(scan(css), [])

    def test_non_hex_palettes_are_skipped_rather_than_guessed_at(self):
        css = block(
            background="color-mix(in oklab, canvas 90%, black)",
            **{
                "--backend-surface": "var(--some-token)",
                "--backend-surface-alt": "oklch(0.2 0.05 250)",
            },
        )
        self.assertEqual(scan(css), [])


class TheAllowMarkerTests(unittest.TestCase):
    def test_marker_suppresses_a_deliberate_two_hue_theme(self):
        css = (
            "body.portal-backend-probe {\n"
            "  /* theme-hue-allow: duotone by design, signed off */\n"
            "  background: #030712;\n"
            "  --backend-surface: #1a1612;\n"
            "  --backend-surface-alt: #241e18;\n"
            "}"
        )
        self.assertEqual(scan(css), [])


class HueMathTests(unittest.TestCase):
    def test_known_hues(self):
        self.assertAlmostEqual(gate._hue((255, 0, 0)), 0.0, places=1)
        self.assertAlmostEqual(gate._hue((0, 255, 0)), 120.0, places=1)
        self.assertAlmostEqual(gate._hue((0, 0, 255)), 240.0, places=1)

    def test_circular_gap_wraps_the_short_way(self):
        self.assertAlmostEqual(gate._circular_gap(350.0, 10.0), 20.0, places=1)
        self.assertAlmostEqual(gate._circular_gap(10.0, 350.0), 20.0, places=1)

    def test_grey_has_no_chroma(self):
        self.assertEqual(gate._chroma((23, 23, 23)), 0)


class SelectorShapeTests(unittest.TestCase):
    """The gate's first version could not see the file that held a real bug."""

    MULTI_SELECTOR = 'body.portal-backend-probe,\nbody.portal-backend-probe[data-bs-theme="dark"],\nbody.portal-backend-probe[data-bs-theme="light"] {\n  background: #f8f4fc;\n  --backend-surface: #ffffff;\n  --backend-surface-alt: #fffaf0;\n}'
    SHIPPED_BACKEND_LIGHT = 'body.portal-backend-light,\nbody.portal-backend-light[data-bs-theme="light"] {\n  background: linear-gradient(135deg, #f8f4fc 0%, #fff 50%, #faf5ff 100%);\n  color: #1a1a2e;\n  --backend-text: #1a1612;\n  --backend-text-muted: #544d44;\n  --backend-surface: #ffffff;\n  --backend-surface-alt: #fffaf0;\n}'
    REFERENCE_ONLY = 'body.portal-backend-ink .card,\nbody.portal-backend-ink input {\n  background-color: var(--backend-surface-alt) !important;\n  color: #241e18;\n  border-color: #030712;\n}'

    def test_a_multi_selector_theme_block_is_scanned(self):
        """backend-light-theme.css opens with a three-selector list; requiring the
        theme name to sit immediately before the brace skipped the whole file."""
        findings = scan(self.MULTI_SELECTOR)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["theme"], "probe")

    def test_the_shipped_backend_light_values_are_a_finding(self):
        """Pinned literally: a lavender ground over an entirely warm ramp."""
        self.assertEqual(len(scan(self.SHIPPED_BACKEND_LIGHT)), 1)

    def test_referencing_a_surface_token_is_not_defining_one(self):
        """background: var(--backend-surface-alt) contains the token name.
        Treating that as a palette makes every component rule a theme.
        """
        self.assertEqual(scan(self.REFERENCE_ONLY), [])


class TheLiveTreeTests(unittest.TestCase):
    """Calibration against the real stylesheets, not a synthetic fixture."""

    def test_the_real_backend_themes_file_is_actually_read(self):
        """Guards the 'gate that scans nothing and reports zero' failure."""
        css = (REPO_ROOT / "static" / "css" / "backend-themes.css").read_text(
            encoding="utf-8"
        )
        blocks = [
            m
            for m in gate._RULE.finditer(css)
            if gate._THEME_SELECTOR.search(m.group(1))
            and gate._DEFINES_SURFACE.search(m.group(2))
        ]
        self.assertGreaterEqual(len(blocks), 12, "theme blocks stopped being matched")

    def test_the_sibling_theme_files_are_read_too(self):
        """The first version of the gate matched zero blocks in BOTH of these, because
        each opens with a multi-selector list. The bug it missed was real."""
        for name in ("backend-light-theme.css", "backend-dark-theme.css"):
            css = (REPO_ROOT / "static" / "css" / name).read_text(encoding="utf-8")
            blocks = [
                m
                for m in gate._RULE.finditer(css)
                if gate._THEME_SELECTOR.search(m.group(1))
                and gate._DEFINES_SURFACE.search(m.group(2))
            ]
            self.assertGreaterEqual(len(blocks), 1, f"{name} is not being scanned")

    def test_the_tree_is_clean(self):
        findings = gate.scan()
        self.assertEqual(
            findings, [], f"theme hue coherence regressed: {findings}"
        )


if __name__ == "__main__":
    unittest.main()
