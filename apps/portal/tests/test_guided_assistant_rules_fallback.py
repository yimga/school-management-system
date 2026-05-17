"""Guided assistants must return structured answers in rules-only mode."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.people.models import TeacherProfile
from apps.siteconfig.models import Plan
from apps.schools.models import School
from services.ai_gateway import TaskType, invoke

_T_HOST = "guidedai.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST],
    AI_GATEWAY_ENABLED=True,
    AI_ALLOW_RULES_FALLBACK=True,
)
class GuidedAssistantRulesFallbackTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Free", slug="basic", is_active=True)
        cls.school = School.objects.create(
            name="Guided AI School",
            slug="guidedai",
            subdomain="guidedai",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def _staff_client(self):
        u = User.objects.create_user(
            username=f"guided_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        TeacherProfile.objects.create(
            user=u,
            school=self.school,
            staff_id=f"G{uuid.uuid4().hex[:4].upper()}",
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        return c

    @patch("services.ai_gateway._call_ollama", return_value=(None, {"error": "unavailable"}))
    def test_invoke_rules_returns_guided_dict(self, _mock_ollama):
        result, meta = invoke(
            TaskType.INTEROP_ASSISTANT,
            "Assist",
            user_query="How do I connect OneRoster?",
            response_schema="guided_assistant",
            metadata={"rag_snippets": [{"scope": "help", "metadata": {"source": "interop"}}]},
        )
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result.get("summary") or ""), 40)
        self.assertEqual(meta.get("provider"), "rules")

    @patch("apps.portal.views_ai_gateway.get_embedding_for_text", return_value=None)
    @patch("apps.portal.views_ai_gateway.AIMemoryService.search_similar", return_value=[])
    @patch("services.ai_gateway._call_ollama", return_value=(None, {"error": "unavailable"}))
    def test_interop_assistant_api_returns_nonempty_summary(
        self, _mock_ollama, _mock_search, _mock_emb
    ):
        from django.test import RequestFactory

        from apps.portal.views_ai_gateway import api_interop_assistant

        user = User.objects.create_user(
            username=f"guided_api_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        request = RequestFactory().post(
            "/api/ai/interop-assistant/",
            data=json.dumps({"query": "Where is the district interop hub?"}),
            content_type="application/json",
        )
        request.user = user
        request.school = self.school
        raw = api_interop_assistant.__wrapped__.__wrapped__.__wrapped__
        resp = raw(request)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertTrue(payload.get("success"))
        summary = (payload.get("guided") or {}).get("summary") or ""
        self.assertGreater(len(summary), 40, summary)

    @patch("apps.portal.views_ai_gateway.get_embedding_for_text", return_value=None)
    @patch("apps.portal.views_ai_gateway.AIMemoryService.search_similar", return_value=[])
    @patch("services.ai_gateway._call_ollama", return_value=(None, {"error": "unavailable"}))
    def test_guided_assistant_endpoints_rules_mode_nonempty(
        self, _mock_ollama, _mock_search, _mock_emb
    ):
        """Plan §5 Phase C: representative guided endpoints return useful copy without Ollama."""
        client = self._staff_client()
        cases = (
            ("api:ai-interop-assistant", "Where is district interop configured?"),
            ("api:ai-studio-os-assistant", "How do I theme the portal shell?"),
            ("api:ai-observability-assistant", "Where do I check SLO dashboards?"),
            ("api:ai-trust-compliance-assistant", "What should we document for FERPA readiness?"),
        )
        for url_name, query in cases:
            with self.subTest(url_name=url_name):
                url = reverse(url_name, urlconf="config.tenant_urls")
                resp = client.post(
                    url,
                    data=json.dumps({"query": query}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200, resp.content)
                payload = resp.json()
                self.assertTrue(payload.get("success"), payload)
                summary = (payload.get("guided") or {}).get("summary") or ""
                self.assertGreater(len(summary), 40, summary)
