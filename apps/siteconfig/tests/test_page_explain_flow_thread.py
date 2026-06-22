"""Flow Thread merge — the page-explain bar folds the system "next action" in.

Covers the two-template contract:
  * rmc_page_explain_strip.html renders the Flow Thread destination (origin dot,
    connector, next-step pill) only when a system next-action is available, and
    marks request.rmc_page_explain_bar_present as it renders, and
  * next_action_strip.html suppresses itself whenever the bar is PRESENT on the
    page (request.rmc_page_explain_bar_present) — regardless of whether an action
    was available — so the action renders exactly once, with no double strip, and
    the standalone still renders (with its own fallback) on shells that do NOT
    mount the bar, so a next-action is never erased there.

render_to_string with an explicit context (no context processors) keeps these
deterministic and DB-free.
"""

from types import SimpleNamespace

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

_THEN = {
    "action_url": "/super/billing/",
    "title": "Reconcile billing",
    "description": "Close the open invoices for the month.",
    "type": "billing",
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

    def test_suppressed_when_bar_present(self):
        # The bar is mounted on this page (it marked the request) -> the bar owns
        # the action and the standalone strip is silent. The merge.
        html = self._strip(
            {
                "rmc_page_explain_enabled": True,
                "request": SimpleNamespace(rmc_page_explain_bar_present=True),
            }
        )
        self.assertNotIn("rmc-next-action-strip", html)
        self.assertNotIn("rmc-nas-chip", html)

    def test_suppressed_when_bar_present_even_without_action(self):
        # The merge holds platform-wide even when the engine returned no rows: the
        # bar still owns the band, so the standalone never doubles up beneath it
        # with a fallback strip. (This is the exact bug owners saw on /configuration/,
        # /studio/, /help-center/: bar with no pill + a separate "Next up" block.)
        html = self._strip(
            {
                "rmc_page_explain_enabled": True,
                "rmc_system_actions": [],
                "rmc_system_actions_available": False,
                "request": SimpleNamespace(rmc_page_explain_bar_present=True),
            }
        )
        self.assertNotIn("rmc-next-action-strip", html)

    def test_renders_standalone_when_bar_absent_but_enabled(self):
        # Bar-less shell (studio embed / developer console / marketing / login):
        # page-explain is enabled platform-wide, but the bar was never mounted here
        # (the request flag is unset) -> the standalone strip still renders, so the
        # next-action is NOT erased. This is what makes keying on bar PRESENCE safe.
        html = self._strip(
            {
                "rmc_page_explain_enabled": True,
                "request": SimpleNamespace(),  # bar never marked the request
            }
        )
        self.assertIn("rmc-next-action-strip", html)
        self.assertIn("School directory", html)

    def test_renders_standalone_without_explain_bar(self):
        # page-explain disabled entirely (e.g. anonymous) -> standalone renders.
        html = self._strip({"rmc_page_explain_enabled": False})
        self.assertIn("rmc-next-action-strip", html)
        self.assertIn("School directory", html)

    def test_bar_marks_request_then_strip_suppresses_end_to_end(self):
        # End-to-end mechanism in production order: rendering the bar (shell chrome,
        # above the content) marks the request, then the standalone strip rendered
        # afterward against the SAME request suppresses itself.
        request = SimpleNamespace()
        render_to_string(
            "components/rmc_page_explain_strip.html",
            {
                "request": request,
                "rmc_page_explain_enabled": True,
                "rmc_page_help": {"title": "Manager dashboard"},
                "rmc_page_workflow_tags": [],
                "rmc_system_actions": [_NEXT],
                "rmc_system_actions_available": True,
            },
        )
        self.assertTrue(getattr(request, "rmc_page_explain_bar_present", False))
        html = self._strip(
            {"rmc_page_explain_enabled": True, "request": request}
        )
        self.assertNotIn("rmc-next-action-strip", html)


class FlowLaunchpadTests(SimpleTestCase):
    """Phase 2: the thread continues from the bar into the reclaimed band."""

    def _launchpad(self, ctx):
        base = {
            "rmc_page_explain_enabled": True,
            "rmc_system_actions_available": True,
            "rmc_conversion_single_action_enforced": False,
            "rmc_system_actions": [_NEXT, _THEN],
        }
        base.update(ctx)
        return render_to_string("components/rmc_flow_launchpad.html", base)

    def test_launchpad_renders_steps_when_multiple_actions(self):
        html = self._launchpad({})
        self.assertIn("rmc-flow-launchpad", html)
        self.assertIn("rmc-flow-launchpad__step--live", html)  # first step is the live anchor
        self.assertIn("School directory", html)  # echoes the pill
        self.assertIn("Reconcile billing", html)  # the next step in the flow
        self.assertIn('href="/super/billing/"', html)
        self.assertIn('aria-current="step"', html)
        # the launchpad never claims the page's single primary action (the pill owns it)
        self.assertNotIn('data-rmc-primary-action="1"', html)

    def test_launchpad_silent_with_single_action(self):
        # only the pill's action -> the bar tells the whole story, no band.
        html = self._launchpad({"rmc_system_actions": [_NEXT]})
        self.assertNotIn("rmc-flow-launchpad", html)

    def test_launchpad_silent_in_strict_mode(self):
        # conversion-single-action focus suppresses the launchpad entirely.
        html = self._launchpad({"rmc_conversion_single_action_enforced": True})
        self.assertNotIn("rmc-flow-launchpad", html)

    def test_launchpad_silent_without_explain_bar(self):
        html = self._launchpad({"rmc_page_explain_enabled": False})
        self.assertNotIn("rmc-flow-launchpad", html)

    def test_launchpad_caps_at_three_steps(self):
        five = [dict(_NEXT, title=f"Action {i}", action_url=f"/a/{i}/") for i in range(5)]
        html = self._launchpad({"rmc_system_actions": five})
        self.assertEqual(html.count("rmc-flow-launchpad__step-link"), 3)

    def test_launchpad_emits_has_hook_attribute(self):
        # The CSS-only operator-header lead-in
        # (body:has([data-rmc-flow-launchpad]) .rmc-page__header) depends on this
        # attribute. Lock the contract so the hook can't silently disappear.
        html = self._launchpad({})
        self.assertIn("data-rmc-flow-launchpad", html)
        # ...and it must NOT be emitted when the launchpad is silent (single action),
        # otherwise the operator headers would get an orphan spine.
        silent = self._launchpad({"rmc_system_actions": [_NEXT]})
        self.assertNotIn("data-rmc-flow-launchpad", silent)


class FlowLeadInTests(SimpleTestCase):
    """Phase 3: the shared hero receives the flow only when the launchpad is above it."""

    def _hero(self, ctx):
        user = SimpleNamespace(
            get_short_name=lambda: "Amara", username="amara", is_authenticated=True
        )
        base = {
            "request": SimpleNamespace(user=user),
            "tp_greeting_role": "ADMIN",
            "portal_quick_actions": [],
            "rmc_page_explain_enabled": True,
            "rmc_conversion_single_action_enforced": False,
            "rmc_system_actions_available": True,
            "rmc_system_actions": [_NEXT, _THEN],
        }
        base.update(ctx)
        return render_to_string("partials/tenant/hero_greeting.html", base)

    def test_hero_receives_leadin_when_launchpad_present(self):
        html = self._hero({})
        self.assertIn("rmc-flow-leadin", html)
        self.assertIn("tp-page-h1", html)  # hero still renders normally

    def test_hero_no_leadin_without_flow(self):
        html = self._hero(
            {"rmc_system_actions_available": False, "rmc_system_actions": []}
        )
        self.assertNotIn("rmc-flow-leadin", html)

    def test_hero_no_leadin_with_single_action(self):
        # one action -> launchpad silent -> no rail above -> hero stays plain.
        html = self._hero({"rmc_system_actions": [_NEXT]})
        self.assertNotIn("rmc-flow-leadin", html)

    def test_hero_no_leadin_in_strict_mode(self):
        html = self._hero({"rmc_conversion_single_action_enforced": True})
        self.assertNotIn("rmc-flow-leadin", html)


class PageHeaderLeadInTests(SimpleTestCase):
    """Phase 3b: the shared page-header partials receive the flow on deep pages."""

    _PARTIALS = ("components/page_header.html", "studio_os/components/page_header.html")

    def _hdr(self, tpl, ctx):
        base = {
            "title": "Wedge registry",
            "subtitle": "42 wedges",
            "eyebrow": "Operator",
            "rmc_page_explain_enabled": True,
            "rmc_conversion_single_action_enforced": False,
            "rmc_system_actions_available": True,
            "rmc_system_actions": [_NEXT, _THEN],
        }
        base.update(ctx)
        return render_to_string(tpl, base)

    def test_both_partials_receive_leadin(self):
        for tpl in self._PARTIALS:
            html = self._hdr(tpl, {})
            self.assertIn("rmc-flow-leadin", html, tpl)
            self.assertIn("Wedge registry", html, tpl)  # header still renders its title

    def test_no_leadin_with_single_action(self):
        for tpl in self._PARTIALS:
            html = self._hdr(tpl, {"rmc_system_actions": [_NEXT]})
            self.assertNotIn("rmc-flow-leadin", html, tpl)

    def test_no_leadin_in_strict_mode(self):
        for tpl in self._PARTIALS:
            html = self._hdr(tpl, {"rmc_conversion_single_action_enforced": True})
            self.assertNotIn("rmc-flow-leadin", html, tpl)

    def test_no_leadin_without_explain_bar(self):
        for tpl in self._PARTIALS:
            html = self._hdr(tpl, {"rmc_page_explain_enabled": False})
            self.assertNotIn("rmc-flow-leadin", html, tpl)
