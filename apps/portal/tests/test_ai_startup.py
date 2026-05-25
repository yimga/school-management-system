"""Tests for AI startup probe gating and logging."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.portal.ai_provider import log_ai_startup_posture
from apps.portal.ai_startup import management_command_skips_ai_startup_probe


class ManagementCommandSkipTests(SimpleTestCase):
    @patch("sys.argv", ["manage.py", "migrate_schemas", "--tenant", "--noinput"])
    def test_migrate_schemas_skips_probe(self):
        self.assertTrue(management_command_skips_ai_startup_probe())

    @patch("sys.argv", ["manage.py", "ensure_tenant_schemas"])
    def test_ensure_tenant_schemas_skips_probe(self):
        self.assertTrue(management_command_skips_ai_startup_probe())

    @patch("sys.argv", ["manage.py", "runserver"])
    def test_runserver_does_not_skip(self):
        self.assertFalse(management_command_skips_ai_startup_probe())


class LogAiStartupPostureTests(SimpleTestCase):
    @patch("apps.portal.ai_provider.logger")
    def test_live_litellm_message(self, mock_logger):
        log_ai_startup_posture(
            health={
                "reachable": True,
                "provider": "litellm",
                "deployment_profile": "online",
            },
            conn={"base_url": "http://127.0.0.1:11434", "discovery_source": "unreachable-default"},
        )
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        self.assertIn("cloud AI", msg)
        self.assertNotIn("Ollama at", msg)

    @patch("apps.portal.ai_provider.logger")
    def test_live_ollama_message(self, mock_logger):
        log_ai_startup_posture(
            health={"reachable": True, "provider": "ollama"},
            conn={
                "base_url": "http://127.0.0.1:11434",
                "discovery_source": "http://127.0.0.1:11434",
            },
        )
        mock_logger.info.assert_called_once()
        self.assertIn("live Ollama", mock_logger.info.call_args[0][0])

    @override_settings(OLLAMA_REQUIRE_LIVE=False, AI_ALLOW_RULES_FALLBACK=True)
    @patch("apps.portal.ai_provider.logger")
    def test_fallback_warning(self, mock_logger):
        log_ai_startup_posture(
            health={
                "reachable": False,
                "provider": "rules",
                "deployment_profile": "online",
            },
            conn={"base_url": "http://127.0.0.1:11434"},
        )
        mock_logger.warning.assert_called_once()
        self.assertIn("grounded fallback", mock_logger.warning.call_args[0][0])
