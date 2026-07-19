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
        os.environ["OPENAI_API_KEY"] = "openai-secret-should-not-render"
        os.environ["OLLAMA_ENDPOINT"] = "http://internal-ollama:11434/api/generate"
        self.addCleanup(os.environ.pop, "OPENAI_API_KEY", None)
        self.addCleanup(os.environ.pop, "OLLAMA_ENDPOINT", None)

        request = self.factory.get("/api/ai-copilot/config/")
        request.user = self.user
        response = ai_copilot_config(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        provider_status = payload.get("provider_status", {})
        self.assertTrue(payload.get("success"))
        self.assertIn("providers", provider_status)
        self.assertNotIn("openai-secret-should-not-render", str(payload))
        self.assertNotIn("internal-ollama", str(payload))
        self.assertEqual(
            provider_status["providers"]["ollama"]["exposure"],
            "local",
        )
        # Local Ollama must be present; cloud providers may also appear when
        # LITELLM_* / deployment posture is configured in the operator env.
        self.assertIn("ollama", provider_status["providers"])
        self.assertNotIn("openai-secret-should-not-render", str(payload))
        self.assertNotIn("api_key", str(provider_status).lower())
