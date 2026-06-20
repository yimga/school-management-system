"""Flow Thread merge — the page-explain bar folds the system "next action" in.

Covers the two-template contract:
  * rmc_page_explain_strip.html renders the Flow Thread destination (origin dot,
    connector, next-step pill) only when a system next-action is available, and
  * next_action_strip.html suppresses itself whenever the bar is hosting that
    action (page-explain enabled AND a system action available) — so the action
    renders exactly once, with no double strip.

render_to_string with an explicit context (no context processors) keeps these
deterministic and DB-free.
"""

from django.template.loader import render_to_string
from django.test import SimpleTestCase

_NEXT = {
    "action_url": "/super/schools/",
    "title": "School directory",
    "description": "Query tenants, open Tenant 360, and run lifecycle actions.",
    "type": "system_health",
    "source": "role_default",
    "urgency": "normal",
    "recommendation_key": "",
    "task_code": "",
}


class PageExplainFlowThreadTests(SimpleTestCase):
    def _explain(self, ctx):
        base = {
            "rmc_page_explain_enabled": True,
            "rmc_page_help": {"title": "Manager dashboard"},
            "rmc_page_workflow_tags": [],
        }
        base.update(ctx)
        return render_to_string("components/rmc_page_explain_strip.html", base)

    def test_flow_thread_renders_with_next_action(self):
        html = self._explain(
            {"rmc_system_actions": [_NEXT], "rmc_system_actions_available": True}
        )
        self.assertIn("rmc-page-explain-strip--flow", html)
        self.assertIn("rmc-page-explain-strip__here-dot", html)
        self.assertIn("rmc-page-explain-strip__flow", html)
        self.assertIn("rmc-page-explain-strip__next", html)
        self.assertIn("School directory", html)
        self.assertIn('href="/super/schools/"', html)
        self.assertIn('data-rmc-primary-action="1"', html)
        # identity is still present (nothing lost from the original bar)
        self.assertIn("About this page", html)
        self.assertIn("Manager dashboard", html)

    def test_no_flow_without_action(self):
        html = self._explain(
            {"rmc_system_actions": [], "rmc_system_actions_available": False}
        )
        self.assertNotIn("rmc-page-explain-strip--flow", html)
        self.assertNotIn("rmc-page-explain-strip__next", html)
        # the plain explain bar still renders
        self.assertIn("About this page", html)
        self.assertIn("Manager dashboard", html)

    def test_disabled_renders_nothing(self):
        html = self._explain({"rmc_page_explain_enabled": False})
        self.assertNotIn("rmc-page-explain-strip", html)


class NextActionStripDedupTests(SimpleTestCase):
    def _strip(self, ctx):
        base = {
            "rmc_conversion_single_action_enforced": False,
            "rmc_system_actions": [_NEXT],
            "rmc_system_actions_available": True,
        }
        base.update(ctx)
        return render_to_string("components/next_action_strip.html", base)

    def test_suppressed_when_bar_hosts_action(self):
        # page-explain enabled + an action available -> the bar owns it, strip is silent.
        html = self._strip({"rmc_page_explain_enabled": True})
        self.assertNotIn("rmc-next-action-strip", html)
        self.assertNotIn("rmc-nas-chip", html)

    def test_renders_standalone_without_explain_bar(self):
        # no page-explain bar -> the standalone strip still renders (no regression).
        html = self._strip({"rmc_page_explain_enabled": False})
        self.assertIn("rmc-next-action-strip", html)
        self.assertIn("School directory", html)
