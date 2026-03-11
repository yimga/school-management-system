import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.portal.views_ai_gateway import api_policy_explain


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
