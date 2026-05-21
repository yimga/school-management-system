"""Deployment-profile AI posture and gateway tier chains."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.ai_deployment_posture import (
    build_posture_fields,
    default_tier_chain_for_profile,
    is_litellm_configured,
    merge_effective_task_tiers,
    normalize_deployment_profile,
    operator_setup_kind,
)
from services.ai_gateway import TaskType


class AiDeploymentPostureTests(SimpleTestCase):
    @override_settings(RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL="")
    def test_online_without_litellm_uses_ollama_chain(self):
        self.assertEqual(default_tier_chain_for_profile(), ["ollama", "rules"])

    @override_settings(
        RMC_DEPLOYMENT_PROFILE="online",
        LITELLM_PROXY_URL="https://proxy.example/v1",
    )
    def test_online_with_litellm_uses_cloud_chain(self):
        self.assertTrue(is_litellm_configured())
        self.assertEqual(
            default_tier_chain_for_profile(),
            ["litellm", "ollama", "rules"],
        )

    @override_settings(RMC_DEPLOYMENT_PROFILE="edge", LITELLM_PROXY_URL="https://x/v1")
    def test_edge_ignores_litellm_in_default_chain(self):
        self.assertEqual(default_tier_chain_for_profile(), ["ollama", "rules"])

    @override_settings(
        RMC_DEPLOYMENT_PROFILE="hybrid",
        LITELLM_PROXY_URL="https://proxy.example/v1",
    )
    def test_hybrid_includes_litellm_when_configured(self):
        self.assertEqual(
            default_tier_chain_for_profile(),
            ["litellm", "ollama", "rules"],
        )

    @override_settings(RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL="")
    def test_merge_effective_task_tiers_covers_all_tasks(self):
        tiers = merge_effective_task_tiers(None)
        for task in TaskType:
            self.assertIn(task.value, tiers)
            self.assertEqual(tiers[task.value], ["ollama", "rules"])

    @override_settings(
        RMC_DEPLOYMENT_PROFILE="online",
        LITELLM_PROXY_URL="https://proxy.example/v1",
        AI_GATEWAY_TASK_TIERS={"general_chat": ["rules"]},
    )
    def test_custom_override_wins_for_one_task(self):
        tiers = merge_effective_task_tiers(None)
        self.assertEqual(tiers["general_chat"], ["rules"])
        self.assertEqual(tiers["admin_copilot"], ["litellm", "ollama", "rules"])

    def test_normalize_unknown_profile_to_online(self):
        self.assertEqual(normalize_deployment_profile("bogus"), "online")

    def test_posture_live_cloud(self):
        fields = build_posture_fields(
            deployment_profile="online",
            reachable=True,
            provider="litellm",
            litellm_configured=True,
            ollama_configured=False,
            rules_fallback_enabled=True,
            fallback_active=False,
        )
        self.assertEqual(fields["posture_mode"], "live_cloud")
        self.assertEqual(fields["live_provider_kind"], "cloud")

    def test_posture_guided_when_rules_only(self):
        fields = build_posture_fields(
            deployment_profile="online",
            reachable=False,
            provider="rules",
            litellm_configured=True,
            ollama_configured=False,
            rules_fallback_enabled=True,
            fallback_active=True,
        )
        self.assertEqual(fields["posture_mode"], "guided")

    def test_operator_setup_kind_render(self):
        self.assertEqual(operator_setup_kind("online"), "render_cloud")
        self.assertEqual(operator_setup_kind("edge"), "edge_ollama")

    @override_settings(RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL="")
    @patch("services.ai_gateway._call_ollama", return_value=("ok", {"provider": "ollama"}))
    def test_gateway_invoke_uses_profile_tiers(self, _mock_ollama):
        from services.ai_gateway import _task_tiers

        tiers = _task_tiers()
        self.assertEqual(tiers["general_chat"], ["ollama", "rules"])

    @override_settings(LITELLM_PROXY_URL="https://proxy.example/v1")
    def test_live_provider_configured_includes_litellm(self):
        from services.ai_gateway import _live_provider_configured

        self.assertTrue(_live_provider_configured())

    def test_operator_recovery_online_without_litellm(self):
        from services.ai_unavailable import _operator_recovery_detail

        with self.settings(RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL=""):
            detail = _operator_recovery_detail()
        self.assertIn("LITELLM_PROXY_URL", detail)
