"""Studio header B1 compaction contract (2026-06-22).

The Studio header used to stack three rows on the right (Home/grid → search →
Commands) because the `studio-os-search` input was `width:100%` inside a
wrapping flex cluster. B1 merges search + Commands into one command pill that
opens the platform-wide unified ⌘K palette — one row.

These static checks (SimpleTestCase, no DB) lock the fix against regression.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]
STUDIO = REPO_ROOT / "templates" / "studio_os"
SHELLS = [STUDIO / "shell.html", STUDIO / "partials" / "shell_main_content.html"]
PILL = STUDIO / "partials" / "studio_command_pill.html"
LAYOUT_CSS = REPO_ROOT / "static" / "css" / "studio-shell-layout.css"


class StudioHeaderCompactionTests(SimpleTestCase):
    def test_both_shells_include_the_command_pill(self) -> None:
        for shell in SHELLS:
            with self.subTest(shell=shell.name):
                self.assertIn(
                    "studio_os/partials/studio_command_pill.html",
                    shell.read_text(encoding="utf-8"),
                    f"{shell.name} must include the shared command pill.",
                )

    def test_buggy_search_input_is_gone_from_both_shells(self) -> None:
        for shell in SHELLS:
            src = shell.read_text(encoding="utf-8")
            with self.subTest(shell=shell.name):
                self.assertNotIn(
                    'id="studio-global-search"', src,
                    f"{shell.name} still ships the old full-width search input.",
                )
                self.assertNotIn(
                    "studio-os-search", src,
                    f"{shell.name} still references the width:100% search class.",
                )
                self.assertNotIn(
                    'id="studio-command-palette-btn"', src,
                    f"{shell.name} still ships the old separate Commands button.",
                )

    def test_pill_has_no_inline_style(self) -> None:
        # The old search carried an inline style="max-width:16rem"; the pill is
        # token-only CSS.
        self.assertNotIn("style=", PILL.read_text(encoding="utf-8"))

    def test_layout_css_defines_pill_and_drops_buggy_rule(self) -> None:
        css = LAYOUT_CSS.read_text(encoding="utf-8")
        self.assertIn(".studio-cmd-pill", css, "pill grammar must be defined.")
        self.assertNotIn(
            ".studio-os-search {", css,
            "the buggy .studio-os-search width:100% rule must be removed.",
        )

    def test_manager_only_home_preserved(self) -> None:
        # Home is control-plane only; tenants must not see it (unchanged by B1).
        for shell in SHELLS:
            src = shell.read_text(encoding="utf-8")
            with self.subTest(shell=shell.name):
                self.assertIn("request.public_host_kind == 'manager'", src)
