"""Studio OS cross-cutting navigation integrity (v3.54.0, 2026-05-21).

Asserts that the Studio rail, mode cards, command palette entries, and
preview links all resolve to real URL names (no dead reverse() calls)
and that every {% include %}d partial exists on disk.

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


def _list_all_studio_templates() -> list[Path]:
    out: list[Path] = []
    for p in TEMPLATES_STUDIO_OS.rglob("*.html"):
        out.append(p)
    return out


def _strip_comments(src: str) -> str:
    src = re.sub(
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
        "",
        src,
        flags=re.DOTALL,
    )
    src = re.sub(r"\{#.*?#\}", "", src, flags=re.DOTALL)
    src = re.sub(r"<!--.*?-->", "", src, flags=re.DOTALL)
    return src


class StudioRailIntegrityTests(SimpleTestCase):
    """The shell.html studio rail (lines ~71-79 pre-v3.54.0; ~lines may shift)
    must link to all 6 modes."""

    def setUp(self) -> None:
        self.shell_text = SHELL.read_text(encoding="utf-8")

    def test_shell_rail_links_all_six_modes(self) -> None:
        for url_name in (
            "studio_os:shell",
            "studio_os:experience",
            "studio_os:automation",
            "studio_os:output",
            "studio_os:launch",
            "studio_os:control",
        ):
            with self.subTest(url_name=url_name):
                self.assertIn(
                    url_name,
                    self.shell_text,
                    f"shell.html must reference {url_name!r} in the studio rail",
                )


class IncludePathIntegrityTests(SimpleTestCase):
    """Every {% include "studio_os/..." %} target must exist on disk."""

    def test_every_include_target_exists(self) -> None:
        include_re = re.compile(
            r"""\{%\s*include\s+["'](studio_os/[^"']+)["']"""
        )
        seen_misses: list[tuple[str, str]] = []
        for template in _list_all_studio_templates():
            src = _strip_comments(template.read_text(encoding="utf-8"))
            for m in include_re.finditer(src):
                target = m.group(1)
                target_path = REPO_ROOT / "templates" / target
                if not target_path.exists():
                    seen_misses.append((str(template.relative_to(REPO_ROOT)), target))
        if seen_misses:
            lines = "\n".join(f"  {t} includes missing {x}" for t, x in seen_misses)
            self.fail(f"Broken {{% include %}} targets:\n{lines}")


class PreviewPaneIncludedInOwnerSectionTests(SimpleTestCase):
    """Every preview pane partial is referenced by its owner section."""

    PANE_TO_OWNER_SECTION = {
        # pane partial → must be included somewhere under this section's templates
        "experience_live_preview_pane.html": ("experience",),
        "automation_simulation_preview_pane.html": ("automation",),
        "output_readiness_preview_pane.html": ("output",),
        "launch_readiness_preview_pane.html": ("launch",),
        "control_governance_preview_pane.html": ("control",),
        "overview_command_cockpit.html": ("shell.html",),  # included from shell when not current_mode
    }

    def test_each_preview_pane_is_referenced(self) -> None:
        for pane, allowed_owners in self.PANE_TO_OWNER_SECTION.items():
            with self.subTest(pane=pane):
                found_in: list[str] = []
                for template in _list_all_studio_templates():
                    if template.name == pane:
                        continue  # don't count self-reference
                    src = _strip_comments(template.read_text(encoding="utf-8"))
                    if pane in src:
                        found_in.append(template.name)
                self.assertTrue(
                    found_in,
                    f"Preview pane {pane} is not referenced by any other "
                    f"studio_os template. Expected ownership in: {allowed_owners}",
                )


class NoDeadElifInShellTests(SimpleTestCase):
    """v3.54.0 removed the dead duplicate {% elif current_mode == 'launch' %}
    branch (the upper launch branch always won)."""

    def test_no_duplicate_launch_elif_branch_in_shell(self) -> None:
        src = SHELL.read_text(encoding="utf-8")
        # Strip Django {% comment %} and {# ... #} blocks first — the
        # v3.54.0 removal note mentions the dead elif inside a comment
        # which would otherwise trip a naive regex count.
        src = _strip_comments(src)
        # Count occurrences of `current_mode == 'launch'` in elif tokens.
        # One occurrence is correct (the upper launch branch); two would
        # mean the dead duplicate has been re-introduced.
        elif_launch = re.findall(
            r"\{%\s*elif\s+current_mode\s*==\s*['\"]launch['\"]",
            src,
        )
        self.assertLessEqual(
            len(elif_launch), 1,
            f"shell.html has {len(elif_launch)} `{{% elif current_mode == 'launch' %}}` "
            f"branches outside comments. v3.54.0 removed the dead duplicate; "
            f"only the first one is reachable.",
        )


class OverviewBranchInRightRailTests(SimpleTestCase):
    """v3.54.0 added an `{% elif not current_mode %}` branch to the right-rail
    Impact-publish cascade."""

    def test_shell_right_rail_has_overview_branch(self) -> None:
        src = SHELL.read_text(encoding="utf-8")
        self.assertTrue(
            re.search(r"\{%\s*elif\s+not\s+current_mode\s*%\}", src)
            or re.search(r"\{%\s*elif\s+current_mode\s+is\s+None", src),
            "shell.html right-rail must have an Overview branch "
            "({% elif not current_mode %}) so Overview mode gets a real summary "
            "instead of falling through to the generic message.",
        )
