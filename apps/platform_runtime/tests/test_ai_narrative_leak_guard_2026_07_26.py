"""System-AI structured cards must never surface a rules-fallback echo.

Root bug (tenant "Operational risk nudge" card): ``generate_anomaly_risk_nudge``
— and its siblings — displayed whatever ``run_ai_prompt`` returned. When no live
LLM is reachable the gateway degrades to ``_rules_fallback``, which USED TO echo
the raw prompt *context* (a stringified health dict) straight back:
``"Request received: {'status': 'setup_needed', 'score': 43, ...}"``. That raw
Python dict rendered verbatim in the tenant UI.

These tests lock BOTH layers of the fix:
  1. ``_rules_fallback`` no longer echoes its input.
  2. the structured cards keep the model narrative ONLY when a genuinely live
     provider answered (``litellm``/``ollama``); otherwise they fall back to
     their own deterministic, PII-free sentence.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.platform_runtime import ai_system_layer
from apps.platform_runtime.ai_system_layer import _ai_narrative_or
from apps.portal.ai_provider import _rules_fallback


class RulesFallbackNoEchoTests(SimpleTestCase):
    def test_does_not_echo_raw_query(self):
        leaked = str({"status": "setup_needed", "score": 43, "onboarding_percent": 82})
        out = _rules_fallback(leaked)
        self.assertNotIn("Request received", out)
        self.assertNotIn("setup_needed", out)
        self.assertNotIn("onboarding_percent", out)

    def test_empty_query_still_greets_without_echo(self):
        out = _rules_fallback("")
        self.assertTrue(out.strip())
        self.assertNotIn("Request received", out)


class AiNarrativeOrTests(SimpleTestCase):
    DET = "DETERMINISTIC-SENTENCE"

    def test_live_provider_uses_model_text(self):
        for prov in ("litellm", "ollama", "LiteLLM", "  Ollama "):
            self.assertEqual(
                _ai_narrative_or(self.DET, "real llm narrative", {"provider": prov}),
                "real llm narrative",
            )

    def test_non_live_provider_uses_deterministic(self):
        for prov in ("rules", "none", "policy", "error", "disabled", "", None):
            self.assertEqual(
                _ai_narrative_or(self.DET, "fallback echo text", {"provider": prov}),
                self.DET,
            )

    def test_live_but_empty_text_uses_deterministic(self):
        self.assertEqual(_ai_narrative_or(self.DET, "   ", {"provider": "ollama"}), self.DET)

    def test_missing_meta_uses_deterministic(self):
        self.assertEqual(_ai_narrative_or(self.DET, "x", None), self.DET)


class AnomalyNudgeNoLeakTests(SimpleTestCase):
    """End-to-end: the exact card that leaked, with a mocked gateway."""

    def _run(self, provider, text):
        health = {
            "status": "setup_needed",
            "score": 43,
            "onboarding_percent": 82,
            "has_report_schedules": False,
            "student_count": 5,
        }
        with (
            mock.patch.object(ai_system_layer, "calculate_school_health", return_value=health),
            mock.patch.object(ai_system_layer, "get_ai_runtime_config", return_value={"enabled": True}),
            mock.patch.object(ai_system_layer, "run_ai_prompt", return_value=(text, {"provider": provider})),
        ):
            return ai_system_layer.generate_anomaly_risk_nudge(mock.Mock(), user=None)

    def test_rules_fallback_echo_is_never_shown(self):
        rec = self._run("rules", "Request received: {'status': 'setup_needed', 'score': 43}")
        self.assertIsNotNone(rec)
        self.assertNotIn("Request received", rec["explanation"])
        self.assertNotIn("{", rec["explanation"])  # no raw dict repr
        self.assertIn("Signals:", rec["explanation"])  # the deterministic expl

    def test_live_llm_narrative_is_shown(self):
        rec = self._run("ollama", "Enrollment is lagging; finish CCC step 3.")
        self.assertEqual(rec["explanation"], "Enrollment is lagging; finish CCC step 3.")
