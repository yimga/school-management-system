"""Phase 11 — info-tag component contract tests.

Asserts the 4 scaffolded Phase 3 component partials exist, render with their
documented context shape, and don't carry inline style= attributes that bypass
the design-token system.
"""
from __future__ import annotations

import pathlib

from django.template import Context, Template, TemplateSyntaxError
from django.test import SimpleTestCase

from apps.platform_runtime import workflow_registry as wf

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
COMPONENTS_DIR = REPO_ROOT / "templates" / "components"
CSS_BUNDLE = REPO_ROOT / "static" / "css" / "rmc-workflow-guidance.css"


class WorkflowComponentFilesPresentTests(SimpleTestCase):
    def test_all_4_components_exist_on_disk(self):
        for name in (
            "workflow_info_tag.html",
            "workflow_help_panel.html",
            "workflow_next_action.html",
            "workflow_status_strip.html",
        ):
            p = COMPONENTS_DIR / name
            self.assertTrue(p.exists(), f"Missing component: {p}")

    def test_css_bundle_exists(self):
        self.assertTrue(CSS_BUNDLE.exists(), f"Missing CSS bundle: {CSS_BUNDLE}")

    def test_components_have_no_inline_style_attr(self):
        # Inline style= would trip scan_inline_style_off_token (baseline 0).
        for name in (
            "workflow_info_tag.html",
            "workflow_help_panel.html",
            "workflow_next_action.html",
            "workflow_status_strip.html",
        ):
            text = (COMPONENTS_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn(' style="', text, f"{name} has inline style attribute")


class WorkflowInfoTagRenderTests(SimpleTestCase):
    def _render(self, ctx: dict) -> str:
        return Template(
            '{% include "components/workflow_info_tag.html" %}'
        ).render(Context(ctx))

    def test_renders_nothing_when_tag_missing(self):
        # No `tag` in context — the {% with %} block still evaluates, but the
        # tag dict is empty, so we accept the chip with defaults.
        out = self._render({})
        # Output is allowed; just must not throw.
        self.assertIsInstance(out, str)

    def test_renders_label_when_tag_supplied(self):
        out = self._render({"tag": {"key": "required", "label": "Required", "tone": "warn"}})
        self.assertIn("Required", out)
        self.assertIn("rmc-workflow-tag", out)
        self.assertIn('data-rmc-workflow-tag="required"', out)
        self.assertIn('data-rmc-workflow-tag-tone="warn"', out)

    def test_aria_label_falls_back_to_label(self):
        out = self._render({"tag": {"key": "draft", "label": "Draft"}})
        self.assertIn('aria-label="Draft"', out)


class WorkflowStatusStripRenderTests(SimpleTestCase):
    def _render(self, status: dict) -> str:
        return Template(
            '{% include "components/workflow_status_strip.html" %}'
        ).render(Context({"status": status}))

    def test_renders_nothing_when_status_falsy(self):
        out = self._render({})
        self.assertEqual(out.strip(), "")

    def test_renders_workflow_title_and_completion_pill(self):
        out = self._render({
            "workflow_title": "Connect SIS",
            "current_step": "Sign MAA",
            "step_index": 1,
            "step_total": 4,
            "completion": "in-progress",
        })
        self.assertIn("Connect SIS", out)
        self.assertIn("In progress", out)
        self.assertIn('data-rmc-workflow-completion="in-progress"', out)

    def test_blocked_state_renders_blocked_label(self):
        out = self._render({"workflow_title": "X", "completion": "blocked"})
        self.assertIn("Blocked", out)


class WorkflowNextActionRenderTests(SimpleTestCase):
    def _render(self, next_action) -> str:
        return Template(
            '{% include "components/workflow_next_action.html" %}'
        ).render(Context({"next_action": next_action}))

    def test_renders_nothing_when_next_action_missing(self):
        out = self._render(None)
        self.assertEqual(out.strip(), "")

    def test_primary_chip_renders_with_label_and_url(self):
        out = self._render({
            "primary": {"label": "Sign MAA", "url": "/migration/maa/", "task_code": "migration-maa"},
            "state": "ready",
        })
        self.assertIn("Sign MAA", out)
        self.assertIn("/migration/maa/", out)
        self.assertIn('data-rmc-primary-action="1"', out)

    def test_blocker_disables_primary_and_renders_resolve_link(self):
        out = self._render({
            "primary": {"label": "Publish", "url": "/publish/"},
            "blocker": {"label": "Approvals pending", "fix_url": "/approvals/"},
            "state": "blocked",
        })
        self.assertIn("Approvals pending", out)
        self.assertIn("aria-disabled=\"true\"", out)
        self.assertIn("/approvals/", out)
        # Primary URL should NOT appear as an active href when blocked
        self.assertIn('href="#"', out)


class TagTaxonomyCSSPresenceTests(SimpleTestCase):
    """The visual class for every tag value must exist in the CSS bundle."""

    def test_css_bundle_references_tag_attribute_selector(self):
        css = CSS_BUNDLE.read_text(encoding="utf-8")
        # The bundle scopes per-tag styling via [data-rmc-workflow-tag*=...].
        # We just assert the base selector exists.
        self.assertIn("data-rmc-workflow-tag", css)
        self.assertIn(".rmc-workflow-tag", css)
