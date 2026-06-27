"""Tenant AI copilot rail — host-correct transport + onboarding grounding (no DB).

Locks the fix for "the copilot doesn't work on the tenant workspace": the shared
rail template now resolves tenant (`portal:`) endpoints on tenant hosts, and those
endpoints are tenant-scoped, RBAC-gated, and grounded in onboarding state so chat
works (even in rules-fallback mode).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from django.test.client import RequestFactory

from apps.platform_runtime import ai_onboarding_context as onb
from apps.portal import views_copilot_rail as rail

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _authed_post(body: dict | str):
    raw = body if isinstance(body, str) else json.dumps(body)
    req = RequestFactory().post("/portal/copilot/rail/send/", data=raw, content_type="application/json")
    req.user = SimpleNamespace(is_authenticated=True, role="ADMIN")
    req.school = SimpleNamespace(pk=1)
    return req


class OnboardingContextTests(SimpleTestCase):
    def test_empty_when_no_payload(self):
        with mock.patch.object(onb, "_zero_friction", return_value={}):
            self.assertEqual(onb.build_onboarding_context_for_ai(SimpleNamespace(pk=1)), {})
            self.assertEqual(onb.onboarding_insight_cards(SimpleNamespace(pk=1)), [])
            self.assertEqual(onb.onboarding_prompt_preamble(SimpleNamespace(pk=1)), "")

    def test_first_run_payload_shapes_context_and_preamble(self):
        payload = {
            "launch_ready": False,
            "health_score": 6,
            "recommended_next": {"label": "Configure academic year", "link": "/x/"},
            "launch_blockers": [{"label": "Add students", "link": "/s/"}, {"label": "Create fee plan"}],
        }
        with mock.patch.object(onb, "_zero_friction", return_value=payload):
            ctx = onb.build_onboarding_context_for_ai(SimpleNamespace(pk=1))["onboarding_state"]
            self.assertFalse(ctx["launch_ready"])
            self.assertEqual(ctx["health_score"], 6)
            self.assertIn("Add students", ctx["blockers"])
            self.assertEqual(ctx["recommended_next"], "Configure academic year")

            preamble = onb.onboarding_prompt_preamble(SimpleNamespace(pk=1))
            self.assertIn("6%", preamble)
            self.assertIn("Configure academic year", preamble)

            cards = onb.onboarding_insight_cards(SimpleNamespace(pk=1), limit=5)
            self.assertTrue(any(c["title"] == "Setup progress" for c in cards))
            self.assertTrue(any(c["tone"] == "warning" for c in cards))

    def test_launch_ready_tenant_gets_no_cards_or_preamble(self):
        with mock.patch.object(onb, "_zero_friction", return_value={"launch_ready": True, "health_score": 100}):
            self.assertEqual(onb.onboarding_insight_cards(SimpleNamespace(pk=1)), [])
            self.assertEqual(onb.onboarding_prompt_preamble(SimpleNamespace(pk=1)), "")

    def test_never_raises_on_garbage(self):
        with mock.patch.object(onb, "_zero_friction", side_effect=RuntimeError("boom")):
            # _zero_friction is patched to raise, but it's only called inside helpers
            # that catch — the public API must still degrade, not raise.
            self.assertEqual(onb.build_onboarding_context_for_ai(SimpleNamespace(pk=1)), {})


class TenantRailSendTests(SimpleTestCase):
    def test_empty_message_is_400(self):
        resp = rail.TenantCopilotRailSendView.as_view()(_authed_post({"message": "   "}))
        self.assertEqual(resp.status_code, 400)

    def test_bad_json_is_400(self):
        resp = rail.TenantCopilotRailSendView.as_view()(_authed_post("{not json"))
        self.assertEqual(resp.status_code, 400)

    def test_rbac_denied_is_403(self):
        deny = SimpleNamespace(allowed=False, denial_reason="not allowed", metadata={}, prompt="")
        with mock.patch("services.ai_copilot_rbac.prepare_copilot_invoke", return_value=deny):
            resp = rail.TenantCopilotRailSendView.as_view()(_authed_post({"message": "hi"}))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(json.loads(resp.content)["error"], "permission_denied")

    def test_happy_path_returns_reply_and_rules_source(self):
        allow = SimpleNamespace(allowed=True, denial_reason="", metadata={}, prompt="P")
        with mock.patch("services.ai_copilot_rbac.prepare_copilot_invoke", return_value=allow), \
                mock.patch.object(onb, "build_onboarding_context_for_ai", return_value={}), \
                mock.patch.object(onb, "onboarding_prompt_preamble", return_value=""), \
                mock.patch("services.ai_helpers.invoke_with_request",
                           return_value=("Here's your next step.", {"provider": "rules", "tier": "rules"})):
            resp = rail.TenantCopilotRailSendView.as_view()(_authed_post({"message": "what next?"}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data["reply"])
        self.assertEqual(data["source"], "rules")

    def test_unavailable_when_invoke_returns_none(self):
        # Governance ON but the gateway yielded nothing → transient "unavailable".
        allow = SimpleNamespace(allowed=True, denial_reason="", metadata={}, prompt="P")
        with mock.patch("services.ai_copilot_rbac.prepare_copilot_invoke", return_value=allow), \
                mock.patch.object(onb, "build_onboarding_context_for_ai", return_value={}), \
                mock.patch.object(onb, "onboarding_prompt_preamble", return_value=""), \
                mock.patch("apps.platform_runtime.ai_governance.resolve_effective_enabled", return_value=True), \
                mock.patch("services.ai_helpers.invoke_with_request", return_value=None):
            resp = rail.TenantCopilotRailSendView.as_view()(_authed_post({"message": "what next?"}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content)["source"], "unavailable")

    def test_disabled_reply_when_ai_governance_off(self):
        # AI governance OFF (RUNMYCAMPUS_AI_ENABLED unset / tenant disabled) → say so
        # plainly instead of a generic "unavailable" that reads as a broken copilot.
        allow = SimpleNamespace(allowed=True, denial_reason="", metadata={}, prompt="P")
        with mock.patch("services.ai_copilot_rbac.prepare_copilot_invoke", return_value=allow), \
                mock.patch.object(onb, "build_onboarding_context_for_ai", return_value={}), \
                mock.patch.object(onb, "onboarding_prompt_preamble", return_value=""), \
                mock.patch("apps.platform_runtime.ai_governance.resolve_effective_enabled", return_value=False), \
                mock.patch("services.ai_helpers.invoke_with_request", return_value=None):
            resp = rail.TenantCopilotRailSendView.as_view()(_authed_post({"message": "what next?"}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["source"], "disabled")
        self.assertIn("turned off", data["reply"].lower())


class TenantRailContextTests(SimpleTestCase):
    def test_context_returns_onboarding_insights(self):
        req = RequestFactory().get("/portal/copilot/rail/context/")
        req.user = SimpleNamespace(is_authenticated=True)
        req.school = SimpleNamespace(pk=1)
        with mock.patch.object(rail, "_onboarding_insights", return_value=[{"title": "Setup progress", "body": "6%"}]):
            resp = rail.TenantCopilotRailContextView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        # Posture is a value the rail JS understands (drives the pill label).
        self.assertIn(data["posture_mode"], {"guided", "live_cloud", "live_local", "unavailable"})
        self.assertEqual(data["snapshot"]["posture_mode"], data["posture_mode"])
        self.assertEqual(len(data["insights"]), 1)

    def test_insight_cards_carry_js_contract_keys(self):
        # The rail JS renders insight.title/.body and reads insight.source.
        with mock.patch.object(onb, "_zero_friction", return_value={
            "launch_ready": False, "health_score": 6,
            "recommended_next": {"label": "Configure year"},
        }):
            cards = onb.onboarding_insight_cards(SimpleNamespace(pk=1), limit=5)
        self.assertTrue(cards)
        for c in cards:
            self.assertIn("title", c)
            self.assertIn("body", c)
            self.assertEqual(c["source"], "rules")


class TransportWiringTests(SimpleTestCase):
    def test_template_resolves_host_correct_endpoints(self):
        tpl = (_REPO_ROOT / "templates" / "partials" / "cockpit" / "_ai_copilot_rail.html").read_text(encoding="utf-8")
        self.assertIn("portal:copilot_rail_context", tpl)
        self.assertIn("portal:copilot_rail_send", tpl)
        self.assertIn("studio_os:copilot_rail_context", tpl)  # manager branch preserved

    def test_ask_with_ai_is_integrated_into_copilot_rail(self):
        tpl = (_REPO_ROOT / "templates" / "partials" / "cockpit" / "_ai_copilot_rail.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-copilot-tab="help"', tpl)
        self.assertIn('data-rmc-copilot-pane="help"', tpl)
        self.assertIn("data-rmc-kb-ai-panel", tpl)
        self.assertIn("rmc-kb-ai-assistant.js", tpl)

    def test_portal_shell_no_longer_mounts_bottom_ai_panel(self):
        tpl = (_REPO_ROOT / "templates" / "portal_base.html").read_text(encoding="utf-8")
        self.assertIn("rmc-copilot-help-mode.css", tpl)
        self.assertNotIn('include "partials/help_module_inline_assistant.html"', tpl)

    def test_inline_assistant_is_suppressed_when_copilot_rail_enabled(self):
        tpl = (_REPO_ROOT / "templates" / "partials" / "help_module_inline_assistant.html").read_text(encoding="utf-8")
        self.assertIn("not cockpit.ai_copilot_rail.enabled", tpl)

    def test_routes_reverse(self):
        from django.urls import reverse
        for name in ("context", "insights", "send", "send_stream"):
            self.assertTrue(reverse(f"portal:copilot_rail_{name}"))
