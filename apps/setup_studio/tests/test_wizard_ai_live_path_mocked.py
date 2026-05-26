"""Mocked-LIVE wizard AI smoke test — proves the LIVE code path WITHOUT LITELLM env.

Unlike ``scripts/verify_wizard_ai_live_smoke.py`` (an external verifier that
honestly reports posture), this Django test patches
``services.ai_helpers.invoke_with_request`` to simulate a real LIVE gateway
response and asserts the wizard_ai bridge:

1. Successfully parses a LIVE response into ``SmartDefaultsResult``.
2. Reports ``used_fallback=False`` when the LIVE path returns valid JSON.
3. Falls back deterministically when the LIVE path raises / returns junk.
4. Sanitizes context (drops sensitive keys) BEFORE the gateway sees it.

This gives v3.94 the equivalent of a production-readiness smoke test
without needing a live LiteLLM account on dev workstations or CI.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.setup_studio import wizard_ai


class _GatewayTaskType:
    """Minimal stand-in for services.ai_helpers.TaskType."""
    NARRATIVE = "narrative"


def _make_live_response(suggestions: dict, confidence_overall: float = 0.85, rationale: str = ""):
    """Build a tuple (text, meta) shaped like a real ai_helpers response.

    Per wizard_ai.request_smart_defaults parsing contract:
      * The whole parsed dict becomes ``result.suggestions``.
      * ``parsed["confidence"]`` (scalar) → ``result.confidence["overall"]``.
      * ``parsed["rationale_text"]`` → ``result.rationale_text``.
    """
    body = dict(suggestions)
    body["confidence"] = confidence_overall
    body["rationale_text"] = rationale
    return (json.dumps(body), {"provider": "mock-litellm", "model": "claude-opus-4-7"})


class MockedLiveAIPathTests(SimpleTestCase):
    """LIVE path correctness with a mocked gateway."""

    def setUp(self):
        self.mock_path = "services.ai_helpers"

    def test_live_response_parses_and_reports_no_fallback(self):
        # Mock both the gateway entry point + the TaskType enum the bridge imports.
        with patch.dict(
            "sys.modules",
            {"services.ai_helpers": type("M", (), {
                "invoke_with_request": lambda **kwargs: _make_live_response(
                    {"palette_key": "kerala_heritage_emerald", "type_scale_anchor": "comfortable"},
                    confidence_overall=0.92,
                    rationale="Anchored on tropical heritage palette.",
                ),
                "TaskType": _GatewayTaskType,
            })},
        ):
            result = wizard_ai.request_smart_defaults(
                request=None,
                school=None,
                wizard_key="cross_platform_whitelabel_branding",
                step_key="typography_style_scaling",
                prompt_key="prompt.whitelabel.suggest_palette",
                context={"country_code": "CM", "school_type": "secondary"},
                options=[],
            )

        self.assertFalse(result.used_fallback)
        self.assertEqual(result.suggestions["palette_key"], "kerala_heritage_emerald")
        self.assertEqual(result.suggestions["type_scale_anchor"], "comfortable")
        self.assertEqual(result.confidence["overall"], 0.92)
        self.assertEqual(result.rationale_text, "Anchored on tropical heritage palette.")

    def test_gateway_exception_falls_back_deterministically(self):
        def _raise(**kwargs):
            raise RuntimeError("simulated gateway timeout")

        with patch.dict(
            "sys.modules",
            {"services.ai_helpers": type("M", (), {
                "invoke_with_request": _raise,
                "TaskType": _GatewayTaskType,
            })},
        ):
            result = wizard_ai.request_smart_defaults(
                request=None,
                school=None,
                wizard_key="cross_platform_whitelabel_branding",
                step_key="typography_style_scaling",
                prompt_key="prompt.whitelabel.suggest_palette",
                context={"country_code": "CM"},
                options=[],
            )

        self.assertTrue(result.used_fallback)
        # Deterministic fallback should still produce SOMETHING usable.
        self.assertIsInstance(result.suggestions, dict)

    def test_gateway_junk_response_falls_back(self):
        with patch.dict(
            "sys.modules",
            {"services.ai_helpers": type("M", (), {
                "invoke_with_request": lambda **kwargs: ("this is not json", {}),
                "TaskType": _GatewayTaskType,
            })},
        ):
            result = wizard_ai.request_smart_defaults(
                request=None,
                school=None,
                wizard_key="cross_platform_whitelabel_branding",
                step_key="typography_style_scaling",
                prompt_key="prompt.whitelabel.suggest_palette",
                context={"country_code": "CM"},
                options=[],
            )

        self.assertTrue(result.used_fallback)

    def test_context_sanitization_drops_sensitive_keys(self):
        """Verify _sanitize_context removes sensitive fragments before any gateway call."""
        captured: dict = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return _make_live_response({}, {}, "")

        with patch.dict(
            "sys.modules",
            {"services.ai_helpers": type("M", (), {
                "invoke_with_request": _capture,
                "TaskType": _GatewayTaskType,
            })},
        ):
            wizard_ai.request_smart_defaults(
                request=None,
                school=None,
                wizard_key="cross_platform_whitelabel_branding",
                step_key="typography_style_scaling",
                prompt_key="prompt.whitelabel.suggest_palette",
                context={
                    "country_code": "CM",            # safe
                    "school_type": "secondary",      # safe
                    "api_key": "sk-secret-12345",    # sensitive — must be dropped
                    "parent_email": "x@y.z",         # sensitive — must be dropped
                    "student_password_hash": "...",  # sensitive — must be dropped
                    "ifsc": "ABCD0123456",           # sensitive — must be dropped
                },
                options=[],
            )

        # The captured prompt text must NOT contain sensitive values.
        prompt = captured.get("prompt", "")
        self.assertNotIn("sk-secret-12345", prompt)
        self.assertNotIn("x@y.z", prompt)
        self.assertNotIn("ABCD0123456", prompt)
        # And the safe context MUST still be present.
        self.assertIn("CM", prompt)
        self.assertIn("secondary", prompt)
