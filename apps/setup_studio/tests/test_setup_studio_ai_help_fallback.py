"""Setup Studio AI help deterministic fallback."""

from django.test import RequestFactory, SimpleTestCase

from apps.platform_runtime.tenant_ai_help import build_tenant_ai_help_context


class SetupStudioAIHelpFallbackTests(SimpleTestCase):
    def test_offline_fallback_message(self):
        factory = RequestFactory()
        request = factory.get("/setup-studio/")
        request.school = None
        request.user = type("U", (), {"is_authenticated": False})()
        ctx = build_tenant_ai_help_context(request, route_name="setup_studio:launch")
        self.assertIn("tenant_safe_message", ctx)
        self.assertTrue(ctx["deterministic_fallback"] or ctx["offline_mode"])
