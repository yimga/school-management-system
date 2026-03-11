import json
import os
from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from apps.portal.views_ai_copilot import ai_copilot_config


class AiCopilotConfigTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            is_authenticated=True,
            role="ADMIN",
            is_superuser=False,
            is_staff=False,
        )

    def test_config_endpoint_returns_frontend_safe_provider_status(self):
        os.environ["GEMINI_API_KEY"] = "gemini-secret-should-not-render"
        os.environ["OLLAMA_ENDPOINT"] = "http://internal-ollama:11434/api/generate"
        self.addCleanup(os.environ.pop, "GEMINI_API_KEY", None)
        self.addCleanup(os.environ.pop, "OLLAMA_ENDPOINT", None)

        request = self.factory.get("/api/ai-copilot/config/")
        request.user = self.user
        response = ai_copilot_config(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        provider_status = payload.get("provider_status", {})
        self.assertTrue(payload.get("success"))
        self.assertIn("providers", provider_status)
        self.assertNotIn("ollama", provider_status)
        self.assertNotIn("gemini-secret-should-not-render", str(payload))
        self.assertNotIn("internal-ollama", str(payload))
        self.assertEqual(
            provider_status["providers"]["ollama"]["exposure"],
            "local",
        )
        self.assertEqual(
            provider_status["providers"]["gemini"]["exposure"],
            "external",
        )
