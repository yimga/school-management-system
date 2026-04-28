"""AI provider abstraction: disabled by default, no outbound calls."""

import os

from django.test import SimpleTestCase

from apps.platform_runtime.ai_providers import (
    describe_ai_assistant_surfaces,
    get_ai_runtime_config,
)


class AIProvidersTests(SimpleTestCase):
    def test_ai_disabled_by_default_without_env(self):
        prev = os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
        try:
            cfg = get_ai_runtime_config()
            self.assertFalse(cfg["enabled"])
            self.assertEqual(cfg["default_provider"], "disabled")
            self.assertFalse(cfg.get("external_student_pii_allowed"))
            self.assertTrue(cfg.get("tenant_opt_in_required"))
        finally:
            if prev is not None:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    def test_ai_can_be_enabled_via_env_only(self):
        prev = os.environ.get("RUNMYCAMPUS_AI_ENABLED")
        os.environ["RUNMYCAMPUS_AI_ENABLED"] = "1"
        try:
            cfg = get_ai_runtime_config()
            self.assertTrue(cfg["enabled"])
        finally:
            if prev is None:
                os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
            else:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    def test_assistant_surface_keys_stable(self):
        surfaces = describe_ai_assistant_surfaces()
        self.assertIn("config_copilot", surfaces)
        self.assertGreaterEqual(len(surfaces), 4)
