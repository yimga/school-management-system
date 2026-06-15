"""Regression SEALS for the AI consolidation work (docs/AI_AND_SELF_HEALING_CONSOLIDATION_PLAN.md §5).

Each fix in that effort has a loophole a future change could silently re-open. These DB-free
SimpleTestCase guards make every such regression fail loudly:

  * Items 1/8/12 — three surfaces named "copilot"/"AI" that make NO model call must stay
    inference-free, and their honest labels must not silently revert.
  * Item 3 — the hub anomaly-nudge fan-out must stay bounded (no unbounded LLM calls).
  * Item 4 — the tenant AI strip gate flag must keep being emitted by the context processor.
  * Item 5 — the portal "legacy" AI gateway is live shared infra (assist dock depends on it);
    deleting it must trip a test, not break production silently.
  * Item 2 — the hub generative-AI launcher must stay populated and fail safe on bad routes.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

# apps/platform_runtime/tests/<this> -> beta/school-management-system
_REPO = Path(__file__).resolve().parents[3]

# Actual inference calls (NOT availability probes like is_ai_available, which are fine).
_INFERENCE_CALLS = ("invoke_with_request(", "invoke_with_request_stream(", "run_ai_prompt(")


def _read(rel: str) -> str:
    return (_REPO / rel).read_text(encoding="utf-8")


def _func_source(text: str, name: str) -> str:
    """Slice a top-level function body from `def name` to the next top-level `def `."""
    marker = f"def {name}("
    start = text.index(marker)
    rest = text[start + len(marker):]
    nxt = rest.find("\ndef ")
    return text[start: start + len(marker) + (nxt if nxt != -1 else len(rest))]


class RulesAsAIHonestySeals(SimpleTestCase):
    """Items 1/8/12 — surfaces named copilot/AI that make no model call must stay that way."""

    def test_support_copilot_suggestions_make_no_inference_call(self):
        body = _func_source(_read("apps/customersuccess/services.py"), "get_support_copilot_suggestions")
        for token in _INFERENCE_CALLS:
            self.assertNotIn(
                token, body,
                msg=f"support copilot gained {token} — it is labelled 'Suggested support "
                    f"actions' (not AI); either revert the call or relabel it honestly.",
            )

    def test_policy_lookup_makes_no_inference_call(self):
        src = _read("apps/governance/turbo/ai_policy_copilot.py")
        for token in _INFERENCE_CALLS:
            self.assertNotIn(token, src, msg=f"policy matrix lookup gained {token}; relabel if now AI.")

    def test_manager_rail_feed_makes_no_inference_call(self):
        # is_ai_available (reachability probe) is allowed; actual inference is not.
        src = _read("apps/observability/ai_copilot_service.py")
        for token in _INFERENCE_CALLS:
            self.assertNotIn(token, src, msg=f"manager rail feed gained {token}; it is a rules metrics feed.")


class RelabelSeals(SimpleTestCase):
    """The honest labels must not silently revert to the misleading 'copilot' wording."""

    def test_policy_lookup_label_pinned(self):
        t = _read("templates/siteconfig/partials/ai_governance_body.html")
        self.assertIn("Policy matrix lookup", t)
        self.assertNotIn("Policy copilot", t)

    def test_support_label_pinned(self):
        t = _read("templates/customersuccess/support_copilot.html")
        self.assertIn("Suggested support actions", t)
        self.assertNotIn("Support co-pilot", t)


class NudgeFanoutCapSeal(SimpleTestCase):
    """Item 3 — the hub anomaly-nudge computation must stay bounded."""

    def test_cap_defined_and_sane(self):
        from apps.platform_runtime import views_health_autopilot as v

        self.assertIsInstance(v._MAX_NUDGE_SCHOOLS, int)
        self.assertGreaterEqual(v._MAX_NUDGE_SCHOOLS, 1)
        self.assertLessEqual(v._MAX_NUDGE_SCHOOLS, 50)

    def test_nudge_loop_is_bounded(self):
        src = _read("apps/platform_runtime/views_health_autopilot.py")
        self.assertIn("if nudge_attempts < _MAX_NUDGE_SCHOOLS", src)


class StripGateFlagSeal(SimpleTestCase):
    """Item 4 — the context processor must keep emitting the gate flag (else the strip goes dead)."""

    def test_context_processor_emits_flag_on_unauth_path(self):
        from apps.platform_runtime.context_processors import ai_operating_layer_context

        class _Req:
            user = None
            school = None

        out = ai_operating_layer_context(_Req())
        self.assertIn("rmc_ai_layer_enabled", out)
        self.assertFalse(out["rmc_ai_layer_enabled"])

    def test_strip_template_gates_on_flag(self):
        self.assertIn("rmc_ai_layer_enabled", _read("templates/accounts/ai_system_layer_strip.html"))


class PortalGatewayCouplingSeal(SimpleTestCase):
    """Item 5 — the portal 'legacy' AI gateway is live shared infra; deletion must trip a test."""

    def test_ai_stream_route_resolves(self):
        try:
            reverse("portal:ai_stream")
        except NoReverseMatch:
            self.fail("portal:ai_stream must resolve — the assist dock + ai-stream bridge depend on it.")

    def test_assist_dock_depends_on_ai_chrome_config(self):
        self.assertIn("ai_chrome_config", _read("apps/assist_dock/context_processors.py"))

    def test_stream_bridge_loaded_in_viewport_engine(self):
        self.assertIn("rmc-ai-stream-bridge", _read("templates/partials/rmc_viewport_engine.html"))


class HubLauncherSeal(SimpleTestCase):
    """Item 2 — the generative-AI launcher must stay populated and fail safe on bad routes."""

    def test_generative_surfaces_nonempty(self):
        from apps.platform_runtime import views_health_autopilot as v

        self.assertTrue(v._GENERATIVE_SURFACES)

    def test_safe_reverse_fails_safe(self):
        from apps.platform_runtime.views_health_autopilot import _safe_reverse

        self.assertIsNone(_safe_reverse(""))
        self.assertIsNone(_safe_reverse("nonexistent_namespace:route_xyz"))
