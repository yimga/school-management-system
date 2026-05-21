"""Studio OS cross-cutting layout contracts (v3.54.0, 2026-05-21).

Asserts layout invariants across all 6 Studio OS sections in one place.
Each section also has section-specific overflow tests (e.g.
test_experience_overflow_invariants.py); this module is the cross-cutting
backstop that catches regressions in any one section's CSS bundle without
having to enumerate them per-section.

Static-only (SimpleTestCase) — no DB needed. Reads CSS + template files
from disk and asserts the invariants the v3.54.0 wave established.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[3]
CSS_DIR = REPO_ROOT / "static" / "css"
TEMPLATES_STUDIO_OS = REPO_ROOT / "templates" / "studio_os"

PER_SECTION_CSS = [
    "studio-overview-cockpit.css",
    "studio-experience-mode.css",
    "studio-automation-cockpit.css",
    "studio-output-cockpit.css",
    "studio-launch-cockpit.css",
    "studio-control-cockpit.css",
]


class SharedRailOverflowFixTests(SimpleTestCase):
    """The v3.54.0 systemic fix: shared rail link rule must declare overflow safety."""

    def setUp(self) -> None:
        self.rail_css = (CSS_DIR / "studio-mode-rail.css").read_text(encoding="utf-8")

    def test_shared_rail_declares_overflow_wrap(self) -> None:
        self.assertIn(
            "overflow-wrap: anywhere",
            self.rail_css,
            "Shared rail link rule must declare overflow-wrap: anywhere "
            "to prevent long localized labels from pushing horizontal scroll",
        )

    def test_shared_rail_declares_min_width_zero(self) -> None:
        self.assertIn(
            "min-width: 0",
            self.rail_css,
            "Shared rail link rule must declare min-width: 0 so flex children "
            "can shrink below intrinsic content width",
        )

    def test_shared_rail_declares_word_break(self) -> None:
        self.assertIn(
            "word-break: break-word",
            self.rail_css,
            "Shared rail link rule must declare word-break: break-word",
        )

    def test_shared_rail_targets_all_four_mode_rails(self) -> None:
        for rail_class in (
            "experience-rail-link",
            "output-rail-link",
            "automation-rail-link",
            "launch-rail-link",
        ):
            with self.subTest(rail_class=rail_class):
                self.assertIn(rail_class, self.rail_css)


class NoStickyClipTrapTests(SimpleTestCase):
    """v3.27.1 lesson: position: sticky + overflow: hidden = truncation trap.

    Cross-cutting backstop on top of scan_sticky_with_overflow_hidden.py
    baseline 0. Walks all per-section CSS bundles and asserts neither rule
    contains the combination on the same selector.
    """

    def _extract_rules(self, css: str) -> list[tuple[str, str]]:
        # Crude {...} body extractor; good enough for declaration co-presence checks.
        out: list[tuple[str, str]] = []
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            selector = m.group(1).strip()
            body = m.group(2)
            out.append((selector, body))
        return out

    def test_no_sticky_with_overflow_hidden_in_per_section_css(self) -> None:
        for fname in PER_SECTION_CSS:
            path = CSS_DIR / fname
            if not path.exists():
                continue
            css = path.read_text(encoding="utf-8")
            for selector, body in self._extract_rules(css):
                has_sticky = "position: sticky" in body or "position:sticky" in body
                # Both overflow:hidden AND overflow-y:hidden are traps; overflow:auto
                # / overflow-y:auto are legitimate internal-scroll patterns.
                clipped = bool(
                    re.search(r"overflow(?:-y)?\s*:\s*hidden\b", body)
                ) and not bool(
                    re.search(r"overflow(?:-y)?\s*:\s*(?:auto|scroll)\b", body)
                )
                if has_sticky and clipped:
                    self.fail(
                        f"{fname}: selector `{selector}` declares position: sticky "
                        f"AND a vertical clip. v3.27.1 truncation trap — use "
                        f"overflow-y: visible (or auto) instead."
                    )


class PerSectionCssExistsTests(SimpleTestCase):
    """Every section ships a per-section CSS bundle."""

    def test_all_six_section_css_bundles_exist(self) -> None:
        for fname in PER_SECTION_CSS:
            with self.subTest(fname=fname):
                self.assertTrue(
                    (CSS_DIR / fname).exists(),
                    f"missing per-section CSS bundle: {fname}",
                )


class NoFixedPixelWidthOnResponsiveContainersTests(SimpleTestCase):
    """Per-section CSS must not declare fixed-pixel widths that fight the
    workspace_main flex/grid layout."""

    # Selectors that legitimately use fixed pixel sizing (icons, badges,
    # avatars, tiles with controlled aspect-ratio). Anything else with
    # `width: <Npx>` on a structural class is a regression.
    ALLOWED_FIXED_PX_PATTERNS = (
        r"\.rmc-.*__icon",
        r"\.rmc-.*__badge",
        r"\.rmc-.*__avatar",
        r"\.rmc-.*__dot",
        r"\.rmc-.*__chip",
        r"\.rmc-.*-tile",
    )

    def test_no_fixed_pixel_widths_on_responsive_containers(self) -> None:
        allowed = re.compile("|".join(self.ALLOWED_FIXED_PX_PATTERNS))
        for fname in PER_SECTION_CSS:
            path = CSS_DIR / fname
            if not path.exists():
                continue
            css = path.read_text(encoding="utf-8")
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
                selector = m.group(1).strip()
                body = m.group(2)
                # Look for `width: <N>px` (not max-width, not min-width).
                if not re.search(r"(?<!-)width\s*:\s*\d+(?:\.\d+)?px", body):
                    continue
                # Allow icons / badges / chips / dots / tiles to have fixed sizing.
                if allowed.search(selector):
                    continue
                # Allow max-width-bounded shells (e.g. width: 100%; max-width: 1200px).
                if re.search(r"max-width\s*:", body):
                    continue
                self.fail(
                    f"{fname}: selector `{selector}` declares a fixed-pixel "
                    f"`width:` on a non-icon/badge/chip/tile container. "
                    f"Use percentage or container-query sizing for responsive layout."
                )


class WorkspaceMainPreservesMinWidthZeroTests(SimpleTestCase):
    """The components/workspace_layout.html shipped `.rmc-studio-workspace__main`
    with min-w-0 baked into the template. Cross-cutting backstop in case a
    future edit removes it.
    """

    def test_workspace_layout_main_carries_min_w_0(self) -> None:
        path = TEMPLATES_STUDIO_OS / "components" / "workspace_layout.html"
        self.assertTrue(path.exists())
        src = path.read_text(encoding="utf-8")
        self.assertIn(
            "min-w-0",
            src,
            "workspace_layout.html __main must declare min-w-0 — without it, "
            "flex children cannot shrink and any wide content (token names, "
            "long workflow labels, vendor codes) pushes horizontal scroll.",
        )
