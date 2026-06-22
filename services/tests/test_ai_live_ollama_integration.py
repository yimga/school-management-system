"""
Live Ollama integration — no mocks on inference or gateway tiers.

Skipped when Ollama is unreachable (default local/PR django-tests).
Set RMC_AI_REQUIRE_LIVE=1 to fail instead of skip (CI with Ollama service).

Run:
  ollama serve && ollama pull llama3
  RMC_AI_REQUIRE_LIVE=1 python manage.py test services.tests.test_ai_live_ollama_integration --tag=ai_live_ollama -v 2
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from django.test import SimpleTestCase, tag


def _ollama_reachable() -> bool:
    # Ollama-SPECIFIC /api/tags probe. The generic probe_ai_provider_reachable()
    # reports reachable when a litellm/degraded fallback is up even though Ollama
    # itself is down, which made these live tests FAIL instead of SKIP off-Ollama
    # (e.g. dev boxes / PR CI with a cloud provider configured). Probe the resolved
    # Ollama base directly so the guard matches this module's documented "/api/tags"
    # intent: run only when Ollama truly answers, skip everywhere else.
    from apps.portal.ai_provider import _probe_ollama_base, resolve_ollama_connection

    conn = resolve_ollama_connection(force_refresh=True)
    ok, _status = _probe_ollama_base(conn.get("base_url") or "")
    return ok


def _require_live() -> bool:
    return os.getenv("RMC_AI_REQUIRE_LIVE", "").strip().lower() in ("1", "true", "yes")


def _live_guard() -> None:
    if _ollama_reachable():
        return
    if _require_live():
        raise AssertionError(
            "Live Ollama required (RMC_AI_REQUIRE_LIVE=1) but /api/tags probe failed. "
            "Start Ollama on OLLAMA_ENDPOINT and pull OLLAMA_MODEL."
        )
    raise unittest.SkipTest("Ollama not reachable — start ollama serve and pull model")


@tag("ai_live_ollama")
class LiveOllamaInferenceIntegrationTests(SimpleTestCase):
    """Hits OllamaInferenceService HTTP (/api/generate) directly."""

    def setUp(self):
        _live_guard()

    def test_inference_service_returns_model_text(self):
        from services.inference import OllamaInferenceService

        text, meta = OllamaInferenceService.infer(
            system_prompt="You are a test assistant.",
            user_prompt="Reply with exactly one word: functional",
            use_cache=False,
            strip_pii=False,
        )
        self.assertTrue((text or "").strip(), meta)
        self.assertEqual(meta.get("provider"), "ollama")
        self.assertNotEqual(meta.get("error"), "unavailable")


@tag("ai_live_ollama")
class LiveGatewayInvokeIntegrationTests(SimpleTestCase):
    """Hits services.ai_gateway.invoke with real _call_ollama (audit mocked only)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._audit_patcher = patch("services.ai_gateway._audit_log")
        cls._audit_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._audit_patcher.stop()
        super().tearDownClass()

    def setUp(self):
        _live_guard()

    def test_invoke_general_chat_uses_ollama_tier(self):
        from services.ai_gateway import TaskType, invoke

        text, meta = invoke(
            TaskType.GENERAL_CHAT.value,
            "Reply with exactly: functional",
            user_query="Reply with exactly: functional",
            metadata={"latency_target": 45},
        )
        self.assertIsInstance(text, str)
        self.assertGreater(len((text or "").strip()), 3, msg=repr(meta))
        tier = (meta or {}).get("tier") or (meta or {}).get("provider")
        self.assertEqual(tier, "ollama", meta)
        self.assertFalse((meta or {}).get("fallback"), meta)

    def test_invoke_guided_reaches_ollama_before_rules(self):
        from services.ai_gateway import TaskType, invoke

        result, meta = invoke(
            TaskType.INTEROP_ASSISTANT.value,
            "Where is district interop configured?",
            user_query="Where is district interop configured?",
            response_schema="guided_assistant",
            metadata={"latency_target": 45},
        )
        self.assertIsInstance(result, dict)
        summary = (result or {}).get("summary") or ""
        self.assertGreater(len(summary), 10, msg=repr(meta))
        tier = (meta or {}).get("tier") or (meta or {}).get("provider")
        self.assertEqual(tier, "ollama", meta)
