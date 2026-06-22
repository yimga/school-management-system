"""Studio OS cross-cutting accessibility contracts (v3.54.0, 2026-05-21).

Asserts a11y invariants across all 6 Studio OS sections:
    - Iframes carry title= attribute (screen reader requirement)
    - Skip-link target preserved in shell.html
    - Command palette uses role=dialog + aria-modal + aria-describedby
    - Status badges use color + icon + text (color is never sole signal)
    - Focus-visible outlines preserved in shared rail rule

Static-only (SimpleTestCase) — no DB needed.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_STUDIO_OS = REPO_ROOT / "templates" / "studio_os"
PARTIALS_DIR = TEMPLATES_STUDIO_OS / "partials"
SHELL = TEMPLATES_STUDIO_OS / "shell.html"
RAIL_CSS = REPO_ROOT / "static" / "css" / "studio-mode-rail.css"
# B1 (2026-06-22): the studio-local command overlay was retired in favour of the
# platform-wide unified ⌘K palette. Studio command access is now the in-header
# pill (opens the unified palette) + the unified palette partial itself.
COMMAND_PILL = PARTIALS_DIR / "studio_command_pill.html"
UNIFIED_PALETTE = REPO_ROOT / "templates" / "components" / "rmc_command_palette.html"


def _list_studio_templates() -> list[Path]:
    return list(TEMPLATES_STUDIO_OS.rglob("*.html"))


class IframeTitleAttributeTests(SimpleTestCase):
    """Every <iframe> in studio_os templates carries a title= attribute."""

    def test_every_iframe_has_title_attribute(self) -> None:
        missing: list[tuple[str, str]] = []
        for template in _list_studio_templates():
            src = template.read_text(encoding="utf-8")
            for m in re.finditer(
                r"<iframe\b([^>]*)>",
                src,
                flags=re.IGNORECASE,
            ):
                attrs = m.group(1)
                if "title=" not in attrs:
                    rel = str(template.relative_to(REPO_ROOT))
                    missing.append((rel, attrs.strip()))
        if missing:
            lines = "\n".join(f"  {f}: <iframe {a}>" for f, a in missing)
            self.fail(f"<iframe> elements missing title= attribute:\n{lines}")


class SkipLinkTargetTests(SimpleTestCase):
    """shell.html preserves the skip-link target #studio-canvas."""

    def test_shell_has_skip_link_to_studio_canvas(self) -> None:
        src = SHELL.read_text(encoding="utf-8")
        self.assertIn(
            'href="#studio-canvas"',
            src,
            "shell.html must keep the skip-link target #studio-canvas accessible "
            "at the top of the page for screen-reader / keyboard users.",
        )
        self.assertTrue(
            re.search(r'id="studio-canvas"', src),
            "shell.html must define id=\"studio-canvas\" on the main element.",
        )


class CommandPaletteAriaTests(SimpleTestCase):
    """Studio command access is accessible after the B1 unification:
    the in-header pill is a labelled dialog-trigger, and the unified ⌘K
    palette it opens is a proper role=dialog + aria-modal surface.
    """

    def test_command_pill_is_a_labelled_dialog_trigger(self) -> None:
        src = COMMAND_PILL.read_text(encoding="utf-8")
        btn_m = re.search(r"<button\b[^>]*>", src)
        self.assertIsNotNone(btn_m, "studio_command_pill.html must render a <button>.")
        btn = btn_m.group(0) if btn_m else ""
        for required in (
            "data-rmc-cmdk-open",      # opens the unified palette (engine delegate)
            "data-rmc-cmdk-trigger",   # found + clicked by cockpit/tools-tray lookups
            'aria-haspopup="dialog"',
            "aria-keyshortcuts=",
            "aria-label=",
        ):
            with self.subTest(required=required):
                self.assertIn(
                    required, btn,
                    f"studio command pill <button> missing required hook/a11y: {required}",
                )
        # It must NOT seed a prefix, or it would open with an unexpected query.
        self.assertNotIn(
            "data-rmc-cmdk-prefix", btn,
            "the studio command pill must open the palette clean (no seeded query).",
        )

    def test_unified_palette_is_a_dialog_with_accessible_name(self) -> None:
        src = UNIFIED_PALETTE.read_text(encoding="utf-8")
        m = re.search(r'<div\b[^>]*id="rmc-cmdk"[^>]*>', src)
        self.assertIsNotNone(
            m, "unified palette (#rmc-cmdk) not found in rmc_command_palette.html"
        )
        attrs = m.group(0) if m else ""
        for required in ('role="dialog"', 'aria-modal="true"'):
            with self.subTest(required=required):
                self.assertIn(required, attrs, f"#rmc-cmdk missing: {required}")
        self.assertTrue(
            ("aria-label=" in attrs) or ("aria-describedby=" in attrs),
            "#rmc-cmdk must carry an accessible name (aria-label or aria-describedby).",
        )

    def test_studio_shell_no_longer_ships_the_duplicate_overlay(self) -> None:
        """The retired studio-local overlay must not creep back (it duplicated
        the unified engine and was the second ⌘K-bound dialog on the page)."""
        for path in (SHELL, PARTIALS_DIR / "shell_main_content.html"):
            with self.subTest(template=path.name):
                self.assertNotIn(
                    'id="studio-cmd-palette"', path.read_text(encoding="utf-8"),
                    f"{path.name} should use the unified ⌘K palette, not a local overlay.",
                )


class FocusVisibleOutlineTests(SimpleTestCase):
    """Shared rail rule preserves focus-visible outline.

    A11y bug would be removing the focus-visible :focus-visible rule from
    the shared rail rule, making rail items invisible to keyboard users.
    """

    def test_shared_rail_focus_visible_outline_preserved(self) -> None:
        css = RAIL_CSS.read_text(encoding="utf-8")
        self.assertIn(
            ":focus-visible",
            css,
            "studio-mode-rail.css must keep :focus-visible rule "
            "for keyboard accessibility of rail items.",
        )
        self.assertIn(
            "outline",
            css,
            "studio-mode-rail.css must declare an outline (not just color) "
            "in :focus-visible — keyboard users need a visible ring.",
        )


class StatusBadgeColorAndTextTests(SimpleTestCase):
    """Status badges in new v3.54.0 partials must include text (not just color).

    Heuristic: any element with `class="badge"` or `.badge` styled with a
    token like `text-bg-success-subtle` must have either text content or
    an aria-label.
    """

    PARTIALS = [
        "overview_command_cockpit.html",
        "experience_live_preview_pane.html",
        "automation_simulation_preview_pane.html",
        "output_readiness_preview_pane.html",
        "launch_readiness_preview_pane.html",
        "control_governance_preview_pane.html",
        "studio_guidance_panel.html",
        "cockpit_signal_strip.html",
    ]

    def test_status_badges_carry_text_or_aria_label(self) -> None:
        for fname in self.PARTIALS:
            path = PARTIALS_DIR / fname
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            # Find <span class="... badge ...">...</span>
            for m in re.finditer(
                r'<span\b[^>]*class="[^"]*\bbadge\b[^"]*"([^>]*)>(.*?)</span>',
                src,
                flags=re.DOTALL,
            ):
                attrs, body = m.group(1), m.group(2).strip()
                if body:
                    continue  # has text content
                if "aria-label" in attrs:
                    continue  # has accessible label
                self.fail(
                    f"{fname}: badge with no text content and no aria-label "
                    f"(color is not a sufficient signal for screen readers). "
                    f"Element: {m.group(0)!r}"
                )


class SemanticHeadingOrderTests(SimpleTestCase):
    """v3.54.0 cockpit grids use h2/h3 in semantic order — no h4-jumps without h3."""

    PARTIALS = [
        "overview_command_cockpit.html",
        "experience_live_preview_pane.html",
        "automation_simulation_preview_pane.html",
        "output_readiness_preview_pane.html",
        "launch_readiness_preview_pane.html",
        "control_governance_preview_pane.html",
    ]

    def test_no_heading_level_skip(self) -> None:
        for fname in self.PARTIALS:
            path = PARTIALS_DIR / fname
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            levels = [
                int(m.group(1)) for m in re.finditer(r"<h([1-6])\b", src)
            ]
            if not levels:
                continue
            prev = levels[0]
            for level in levels[1:]:
                # Allow same level, going up, or +1 step. Disallow +2 or more.
                if level > prev + 1:
                    self.fail(
                        f"{fname}: heading level jump h{prev} → h{level} "
                        f"skips a level. Use sequential headings for screen readers."
                    )
                prev = level
