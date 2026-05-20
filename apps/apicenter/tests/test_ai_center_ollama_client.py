"""Ollama client circuit breaker and disabled paths."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from services.ai_center.ollama_client import OllamaAICenterClient


class AICenterOllamaClientTests(SimpleTestCase):
    @override_settings(AI_GATEWAY_ENABLED=False)
    def test_disabled_when_gateway_off(self):
        client = OllamaAICenterClient()
        out = client.generate(system="s", user="u")
        self.assertFalse(out["ok"])
        self.assertEqual(out["provider"], "disabled")

    @override_settings(AI_GATEWAY_ENABLED=True, AI_GATEWAY_PROVIDER="ollama")
    def test_circuit_opens_after_failures(self):
        client = OllamaAICenterClient()
        for _ in range(3):
            client._trip_circuit()
        self.assertTrue(client.circuit_open())
