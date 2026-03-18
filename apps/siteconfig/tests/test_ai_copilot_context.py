import os

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from apps.siteconfig.context_processors import ai_copilot_settings

User = get_user_model()


class AiCopilotContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="ai-admin",
            password="test",
            role=User.Role.ADMIN,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

    def _request(self):
        request = self.factory.get("/authentication/backend/")
        request.user = self.user
        request.session = {}
        return request

    def test_context_processor_exposes_safe_flags_only(self):
        request = self._request()
        with self.settings(AI_ALLOW_RULES_FALLBACK=True):
            ctx = ai_copilot_settings(request)
        self.assertNotIn("GEMINI_API_KEY", ctx)
        self.assertIn("AI_BACKEND_ENABLED", ctx)
        self.assertIn("AI_PROVIDER_NAME", ctx)
        self.assertIn("AI_PERMISSIONS", ctx)

    def test_ai_copilot_template_never_renders_provider_secret(self):
        request = self._request()
        os.environ["GEMINI_API_KEY"] = "gemini-secret-should-not-render"
        self.addCleanup(os.environ.pop, "GEMINI_API_KEY", None)

        context = {
            **ai_copilot_settings(request),
            "csrf_token": "test-csrf-token",
        }
        rendered = render_to_string(
            "components/ai_copilot.html", context=context, request=request
        )

        self.assertNotIn("gemini-secret-should-not-render", rendered)
        self.assertNotIn("GEMINI_API_KEY", rendered)
        self.assertIn("AI_BACKEND_ENABLED", rendered)
