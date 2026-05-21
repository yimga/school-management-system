"""Studio OS cross-cutting live-preview contracts (v3.54.0, 2026-05-21).

Asserts that every Studio OS section ships a live-preview pane partial
with the required contract:
    - Exists on disk
    - Renders an honest empty state (no fabricated data when context absent)
    - No dummy href="#" (every link gated by {% if %})
    - Iframe (if any) carries title= attribute for a11y

Static-only (SimpleTestCase) — no DB needed.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[3]
PARTIALS_DIR = REPO_ROOT / "templates" / "studio_os" / "partials"


PER_SECTION_PREVIEW_PANES = {
    "experience": "experience_live_preview_pane.html",
    "automation": "automation_simulation_preview_pane.html",
    "output": "output_readiness_preview_pane.html",
    "launch": "launch_readiness_preview_pane.html",
    "control": "control_governance_preview_pane.html",
    # Overview surfaces previews via overview_command_cockpit.html triptych.
    "overview": "overview_command_cockpit.html",
}


def _strip_django_comments(src: str) -> str:
    """Remove {% comment %}...{% endcomment %} blocks and {# ... #} comments.

    Allow-markers and example strings inside comments are not real template
    tokens and shouldn't be scanned for href="#".
    """
    src = re.sub(
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
        "",
        src,
        flags=re.DOTALL,
    )
    src = re.sub(r"\{#.*?#\}", "", src, flags=re.DOTALL)
    # Strip <!-- ... --> HTML comments too (some agents used those for docs).
    src = re.sub(r"<!--.*?-->", "", src, flags=re.DOTALL)
    return src


class LivePreviewPaneExistsTests(SimpleTestCase):
    """Every section ships a preview pane partial."""

    def test_all_six_sections_have_a_preview_partial(self) -> None:
        for section, fname in PER_SECTION_PREVIEW_PANES.items():
            with self.subTest(section=section):
                path = PARTIALS_DIR / fname
                self.assertTrue(
                    path.exists(),
                    f"section `{section}` is missing its preview pane partial: {fname}",
                )


class LivePreviewPaneHonestEmptyStateTests(SimpleTestCase):
    """Preview panes must render an honest empty state when context absent.

    Heuristic: file contains at least one {% else %} or {% elif %} branch
    AND at least one piece of "no data yet" / "coming online" / "select a"
    copy. This catches panes that would render a blank pane vs sections
    that intentionally surface the missing-context story.
    """

    EMPTY_STATE_PHRASES = (
        "coming online",
        "no data",
        "no recent",
        "no actions",
        "select a",
        "preview unavailable",
        "no preview",
        "service offline",
        "Choose a mode",
        "service coming",
        "No outputs",
        "Readiness will populate",
    )

    def test_every_preview_pane_has_honest_empty_state(self) -> None:
        for section, fname in PER_SECTION_PREVIEW_PANES.items():
            with self.subTest(section=section):
                path = PARTIALS_DIR / fname
                src = path.read_text(encoding="utf-8")
                # Must have a fallback branch.
                has_branch = bool(
                    re.search(r"\{%\s*(else|elif)\b", src)
                )
                self.assertTrue(
                    has_branch,
                    f"{fname}: preview pane must surface an empty state via "
                    f"{{% else %}} or {{% elif %}} when its context vars are absent",
                )
                # Must contain at least one empty-state phrase.
                hit = any(phrase.lower() in src.lower() for phrase in self.EMPTY_STATE_PHRASES)
                self.assertTrue(
                    hit,
                    f"{fname}: no empty-state copy detected. Expected one of: "
                    f"{', '.join(self.EMPTY_STATE_PHRASES)}",
                )


class LivePreviewPaneNoDummyHrefTests(SimpleTestCase):
    """No href="#" anywhere in preview-pane partials (Django-comment-aware)."""

    def test_no_dummy_hash_links_in_preview_panes(self) -> None:
        for section, fname in PER_SECTION_PREVIEW_PANES.items():
            with self.subTest(section=section):
                path = PARTIALS_DIR / fname
                src = path.read_text(encoding="utf-8")
                stripped = _strip_django_comments(src)
                self.assertNotIn(
                    'href="#"',
                    stripped,
                    f"{fname}: dummy href=\"#\" found outside a comment. "
                    f"Every link must be gated by {{% if url %}} or hidden when absent.",
                )


class LivePreviewIframeAccessibilityTests(SimpleTestCase):
    """Iframes (if any) inside preview panes carry title= for screen readers."""

    def test_iframes_have_title_attribute(self) -> None:
        for section, fname in PER_SECTION_PREVIEW_PANES.items():
            with self.subTest(section=section):
                path = PARTIALS_DIR / fname
                src = path.read_text(encoding="utf-8")
                for m in re.finditer(r"<iframe\b([^>]*)>", src, flags=re.IGNORECASE):
                    attrs = m.group(1)
                    self.assertTrue(
                        "title=" in attrs,
                        f"{fname}: <iframe> missing title= attribute "
                        f"(required for screen readers). attrs: {attrs!r}",
                    )
