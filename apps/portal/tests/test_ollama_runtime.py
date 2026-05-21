"""Ollama auto-start helper (mocked — no real subprocess)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


@override_settings(
    OLLAMA_AUTO_START=True,
    OLLAMA_AUTO_DISCOVER=False,
    OLLAMA_BASE_URL="http://127.0.0.1:11434",
)
class OllamaRuntimeTests(SimpleTestCase):
    @patch("services.ollama_runtime._spawn_ollama_serve", return_value=True)
    @patch("apps.portal.ai_provider._probe_ollama_base", side_effect=[(False, None), (True, 12)])
    @patch("apps.portal.ai_provider.resolve_ollama_connection")
    def test_ensure_reachable_spawns_then_probes(
        self, mock_resolve, mock_probe, _mock_spawn
    ):
        mock_resolve.return_value = {
            "base_url": "http://127.0.0.1:11434",
            "configured": True,
            "discovery_source": "settings",
        }
        from services.ollama_runtime import ensure_ollama_reachable

        self.assertTrue(ensure_ollama_reachable())
        self.assertGreaterEqual(mock_probe.call_count, 2)

    @patch("services.ollama_runtime._ollama_auto_start_enabled", return_value=False)
    @patch("apps.portal.ai_provider._probe_ollama_base", return_value=(False, None))
    @patch("apps.portal.ai_provider.resolve_ollama_connection")
    def test_no_spawn_when_auto_start_disabled(self, mock_resolve, mock_probe, _mock_enabled):
        mock_resolve.return_value = {"base_url": "http://127.0.0.1:11434", "configured": True}
        from services.ollama_runtime import ensure_ollama_reachable

        self.assertFalse(ensure_ollama_reachable())
        mock_probe.assert_called_once()
