"""Smoke + regression guard for the tenant AI strip gating (consolidation §5 item 4).

The AI strip (``accounts/ai_system_layer_strip.html``) is the single tenant AI home.
It must render ONLY when the school's AI assistant is enabled (``rmc_ai_layer_enabled``);
in rules-only mode its rows merely restate richer purpose-built widgets, so it is hidden.
"""

from __future__ import annotations

from django.template.loader import render_to_string
from django.test import SimpleTestCase

_TEMPLATE = "accounts/ai_system_layer_strip.html"
_INSIGHT = {"title": "HEALTH-TITLE-MARKER", "explanation": "some explanation text"}


class AISystemLayerStripGateTests(SimpleTestCase):
    def test_hidden_when_ai_disabled_even_with_insights(self):
        out = render_to_string(
            _TEMPLATE,
            {
                "rmc_ai_layer_enabled": False,
                "rmc_ai_system_health_insight": _INSIGHT,
                "rmc_ai_system_onboarding_insight": _INSIGHT,
                "rmc_ai_anomaly_nudge": _INSIGHT,
            },
        )
        self.assertNotIn("HEALTH-TITLE-MARKER", out)
        self.assertNotIn("data-rmc-ai-system-layer", out)
        self.assertEqual(out.strip(), "")

    def test_shown_when_ai_enabled_with_insight(self):
        out = render_to_string(
            _TEMPLATE,
            {"rmc_ai_layer_enabled": True, "rmc_ai_system_health_insight": _INSIGHT},
        )
        self.assertIn("data-rmc-ai-system-layer", out)
        self.assertIn("HEALTH-TITLE-MARKER", out)
        self.assertIn("AI suggestions", out)

    def test_hidden_when_enabled_but_no_insights(self):
        out = render_to_string(_TEMPLATE, {"rmc_ai_layer_enabled": True})
        self.assertEqual(out.strip(), "")

    def test_missing_flag_defaults_hidden(self):
        # Defensive: if the context processor didn't run, the flag is absent/falsey.
        out = render_to_string(
            _TEMPLATE, {"rmc_ai_system_health_insight": _INSIGHT}
        )
        self.assertEqual(out.strip(), "")
