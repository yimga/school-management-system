"""Fast AI Center posture template contract (no DB)."""

from __future__ import annotations

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings


class AiCenterPostureTemplateTests(SimpleTestCase):
    def _render_body(self, **extra: object) -> str:
        tpl = Template(
            "{% load i18n static %}"
            '{% include "siteconfig/partials/ai_center_body.html" %}'
        )
        provider_status = {
            "reachable": False,
            "rules_fallback_enabled": True,
            "deployment_profile": "online",
            "litellm_configured": True,
            "ollama_configured": False,
            "posture_label": "Guided — help center & maps",
            "gateway_tier_chain": ["litellm", "ollama", "rules"],
            "operator_setup_kind": "render_cloud",
            "providers": {
                "ollama": {"configured": False, "model": None, "exposure": "local"},
                "litellm": {"configured": True, "model": "gpt-5.4-mini", "exposure": "cloud"},
            },
        }
        ctx = {
            "ai_center_shell": "control-plane",
            "provider_status": provider_status,
            "show_operator_ai_setup": True,
            "assistants": [],
            "default_assistant": None,
            "ai_governance_url": None,
            "help_center_url": None,
            "ai_feedback_url": None,
            **extra,
        }
        with self.settings(STATIC_URL="/static/"):
            return tpl.render(Context(ctx))

    def test_online_render_cloud_operator_block(self):
        html = self._render_body()
        self.assertIn("Render SaaS cloud AI", html)
        self.assertIn("LITELLM_PROXY_URL", html)
        self.assertIn("data-rmc-ai-health-root", html)

    @override_settings()
    def test_edge_operator_block_shows_ollama(self):
        html = self._render_body(
            provider_status={
                "reachable": False,
                "rules_fallback_enabled": True,
                "deployment_profile": "edge",
                "litellm_configured": False,
                "ollama_configured": True,
                "posture_label": "Guided — help center & maps",
                "gateway_tier_chain": ["ollama", "rules"],
                "operator_setup_kind": "edge_ollama",
                "providers": {
                    "ollama": {"configured": True, "model": "llama3", "exposure": "local"},
                },
            }
        )
        self.assertIn("ollama serve", html)
        self.assertIn("RMC_DEPLOYMENT_PROFILE=edge", html)
