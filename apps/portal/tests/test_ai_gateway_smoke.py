import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.portal.views_ai_gateway import (
    api_dashboard_pack_recommend,
    api_marketplace_recommend,
    api_policy_explain,
    api_setup_assistant,
)


class AIGatewaySmokeTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            is_authenticated=True,
            id=1,
            role="ADMIN",
        )

    @patch("apps.portal.views_ai_gateway._gateway_response")
    @patch("apps.portal.views_ai_gateway.AIMemoryService.search_similar")
    @patch("apps.portal.views_ai_gateway.get_embedding_for_text")
    @patch("apps.portal.views_ai_gateway.get_prompt_template")
    @patch("apps.portal.views_ai_gateway._check_rate_limit")
    @patch("apps.portal.views_ai_gateway._log_gateway_audit")
    def test_policy_explain_returns_structured_success(
        self,
        mock_audit,
        mock_rate_limit,
        mock_prompt_template,
        mock_embedding,
        mock_search,
        mock_gateway_response,
    ):
        mock_audit.return_value = None
        mock_rate_limit.return_value = (True, 0)
        mock_prompt_template.return_value = "Explain policy in JSON"
        mock_embedding.return_value = [0.1, 0.2]
        mock_search.return_value = [{"metadata": {"policy": "sample"}}]
        mock_gateway_response.return_value = (
            {"summary": "ok", "differences": [], "warnings": []},
            {"provider": "rules"},
        )

        request = self.factory.post(
            "/api/ai-gateway/policy-explain/",
            data=json.dumps({"query": "Explain attendance policy"}),
            content_type="application/json",
        )
        request.user = self.user
        request.school = SimpleNamespace(id=11)
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "test-agent"

        raw_view = api_policy_explain.__wrapped__.__wrapped__.__wrapped__
        response = raw_view(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["explanation"]["summary"], "ok")

    @patch("apps.portal.views_ai_gateway._gateway_response")
    @patch("apps.portal.views_ai_gateway.AIMemoryService.search_similar")
    @patch("apps.portal.views_ai_gateway.get_embedding_for_text")
    @patch("apps.portal.views_ai_gateway.get_prompt_template")
    @patch("apps.portal.views_ai_gateway._check_rate_limit")
    @patch("apps.portal.views_ai_gateway._log_gateway_audit")
    def test_setup_assistant_uses_help_and_config_scopes(
        self,
        mock_audit,
        mock_rate_limit,
        mock_prompt_template,
        mock_embedding,
        mock_search,
        mock_gateway_response,
    ):
        mock_audit.return_value = None
        mock_rate_limit.return_value = (True, 0)
        mock_prompt_template.return_value = "Help answer"
        mock_embedding.return_value = [0.1, 0.2]
        mock_search.side_effect = [
            [{"id": 1, "metadata": {"source": "setup"}}],
            [{"id": 2, "metadata": {"source": "config"}}],
            [],
        ]
        mock_gateway_response.return_value = (
            "Start with branding and import data.",
            {"provider": "ollama", "tier": "ollama", "task_type": "setup_recommend", "request_id": "req-1"},
        )

        request = self.factory.post(
            "/api/ai/setup-assistant/",
            data=json.dumps({"query": "How do I finish setup?"}),
            content_type="application/json",
        )
        request.user = self.user
        request.school = SimpleNamespace(id=11)
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "test-agent"

        raw_view = api_setup_assistant.__wrapped__.__wrapped__.__wrapped__
        response = raw_view(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["success"])
        self.assertEqual([call.args[1] for call in mock_search.call_args_list], ["help", "config", "default"])

    @patch("apps.portal.views_ai_gateway._gateway_response")
    @patch("apps.portal.views_ai_gateway.get_prompt_template")
    @patch("apps.portal.views_ai_gateway._check_rate_limit")
    @patch("apps.portal.views_ai_gateway._log_gateway_audit")
    def test_dashboard_pack_recommend_returns_structured_payload(
        self,
        mock_audit,
        mock_rate_limit,
        mock_prompt_template,
        mock_gateway_response,
    ):
        mock_audit.return_value = None
        mock_rate_limit.return_value = (True, 0)
        mock_prompt_template.return_value = "Recommend dashboards"
        mock_gateway_response.return_value = (
            {"dashboards": [{"title": "Executive Home"}], "packs": [{"title": "Starter"}], "rationale": "Best fit"},
            {"provider": "vllm", "tier": "vllm", "task_type": "setup_recommend", "request_id": "req-2"},
        )

        request = self.factory.post(
            "/api/ai/dashboard-pack-recommend/",
            data=json.dumps({"query": "District leadership rollout"}),
            content_type="application/json",
        )
        request.user = self.user
        request.school = SimpleNamespace(id=11)

        raw_view = api_dashboard_pack_recommend.__wrapped__.__wrapped__.__wrapped__
        response = raw_view(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["dashboards"][0]["title"], "Executive Home")
        self.assertEqual(payload["packs"][0]["title"], "Starter")

    @patch("apps.portal.views_ai_gateway._gateway_response")
    @patch("apps.portal.views_ai_gateway.get_prompt_template")
    @patch("apps.portal.views_ai_gateway._check_rate_limit")
    @patch("apps.portal.views_ai_gateway._log_gateway_audit")
    def test_marketplace_recommend_returns_wave3_payload(
        self,
        mock_audit,
        mock_rate_limit,
        mock_prompt_template,
        mock_gateway_response,
    ):
        mock_audit.return_value = None
        mock_rate_limit.return_value = (True, 0)
        mock_prompt_template.return_value = "Recommend marketplace packs"
        mock_gateway_response.return_value = (
            {"recommendations": [{"title": "Admissions Booster"}], "rationale": "High fit"},
            {"provider": "vllm", "tier": "vllm", "task_type": "setup_recommend", "request_id": "req-3"},
        )

        request = self.factory.post(
            "/api/ai/marketplace-recommend/",
            data=json.dumps({"query": "Private school growth"}),
            content_type="application/json",
        )
        request.user = self.user
        request.school = SimpleNamespace(id=11)

        raw_view = api_marketplace_recommend.__wrapped__.__wrapped__.__wrapped__
        response = raw_view(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["recommendations"][0]["title"], "Admissions Booster")
        self.assertEqual(payload["rationale"], "High fit")
