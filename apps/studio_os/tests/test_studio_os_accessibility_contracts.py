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
    """Command palette uses role=dialog + aria-modal=true + aria-describedby."""

    def test_command_palette_has_dialog_role_and_aria(self) -> None:
        src = SHELL.read_text(encoding="utf-8")
        m = re.search(
            r'<div\b[^>]*id="studio-cmd-palette"[^>]*>',
            src,
        )
        self.assertIsNotNone(
            m, "studio-cmd-palette element not found in shell.html"
        )
        attrs = m.group(0) if m else ""
        for required in ('role="dialog"', 'aria-modal="true"', 'aria-describedby='):
            with self.subTest(required=required):
                self.assertIn(
                    required, attrs,
                    f"studio-cmd-palette missing required a11y attribute: {required}",
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
