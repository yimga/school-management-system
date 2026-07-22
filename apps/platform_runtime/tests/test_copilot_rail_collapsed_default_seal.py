"""Regression SEAL: the AI copilot rail stays COLLAPSED by default, platform-wide.

Fix 75027328b (2026-06-19). The rail was rendering EXPANDED by default on the
flight deck (and any page whose workflow feed auto-pushes context): every shell
already ships ``data-copilot="collapsed"`` and the grid-lock CSS pins the rail to
44px collapsed, but ``rmc-workflow-flight-deck.js`` auto-dispatches
``rmc-workflow-copilot-context`` on load, and the shared handler in
``rmc-copilot-context-lens.js`` called ``fillInput()`` — which itself RE-OPENS the
rail (``setRailTab`` / ``openTenantLensChrome``) → ``data-copilot`` flipped to
``expanded`` every load.

The handler now STAGES the prompt straight into the input (``.value = prompt``)
without opening. These DB-free source seals make a re-open regression fail loudly
rather than silently shipping an always-expanded rail again.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

# tests/ -> platform_runtime/ -> apps/ -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[3]
_JS = _REPO_ROOT / "static" / "js" / "rmc-copilot-context-lens.js"
_APP_SHELL_CSS = _REPO_ROOT / "static" / "css" / "rmc-app-shell.css"
_SHELLS = {
    "control_plane_skeleton.html": _REPO_ROOT / "templates" / "control_plane_skeleton.html",
    "portal_base.html": _REPO_ROOT / "templates" / "portal_base.html",
    "admin/base.html": _REPO_ROOT / "templates" / "admin" / "base.html",
}


class CopilotRailCollapsedDefaultSeals(SimpleTestCase):
    def test_every_shell_defaults_the_rail_to_collapsed(self):
        for name, path in _SHELLS.items():
            html = path.read_text(encoding="utf-8")
            if name == "admin/base.html":
                # Admin intentionally has no global rail (see template comment).
                self.assertNotIn(
                    'data-copilot="expanded"',
                    html,
                    f"{name} must not hardcode an expanded copilot rail",
                )
                continue
            literal = 'data-copilot="collapsed"' in html
            # portal_base binds runtime state with a collapsed template default
            # (onboarding may still expand via cockpit_context — width sealed in CSS).
            templated = (
                "data-copilot=" in html
                and (
                    "|default:'collapsed'" in html
                    or '|default:"collapsed"' in html
                )
            )
            self.assertTrue(
                literal or templated,
                f"{name} must ship the copilot rail collapsed by default "
                f"(literal data-copilot=\"collapsed\" or |default:'collapsed')",
            )

    def _workflow_context_handler(self) -> str:
        """Return just the body of the rmc-workflow-copilot-context listener."""
        js = _JS.read_text(encoding="utf-8")
        idx = js.find('"rmc-workflow-copilot-context"')
        self.assertNotEqual(
            idx, -1, "the rmc-workflow-copilot-context listener has gone missing"
        )
        end = js.find("});", idx)
        self.assertNotEqual(end, -1, "could not delimit the workflow-context handler")
        return js[idx:end]

    def test_workflow_context_stages_prompt_without_opening_the_rail(self):
        block = self._workflow_context_handler()
        # Strip ``//`` line comments first: the handler carries an explanatory note
        # that NAMES fillInput()/openTenantLensChrome() to document why they're
        # avoided, and we must assert on executable code only — not the comment.
        code = "\n".join(line.split("//", 1)[0] for line in block.splitlines())
        # The fix stages the prompt directly into the input element...
        self.assertIn(
            "stageInput",
            code,
            "workflow-context handler must stage the prompt into the input",
        )
        self.assertIn(".value = prompt", code)
        # ...and must NOT call the openers, which re-expand the rail on load.
        self.assertNotIn(
            "fillInput(",
            code,
            "workflow-context handler must not call fillInput() — it re-opens the rail",
        )
        self.assertNotIn(
            "openLensChrome(",
            code,
            "workflow-context handler must not auto-open the copilot on load",
        )

    def test_css_widens_the_rail_only_when_explicitly_expanded(self):
        css = _APP_SHELL_CSS.read_text(encoding="utf-8")
        self.assertIn(
            '[data-copilot="expanded"]',
            css,
            "only the expanded state may widen the rail; collapsed stays the 44px default",
        )
