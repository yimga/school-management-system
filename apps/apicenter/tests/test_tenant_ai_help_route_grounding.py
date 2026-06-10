"""Tenant AI help — route grounding (apicenter contract)."""

from django.test import RequestFactory, SimpleTestCase

from apps.platform_runtime.tenant_ai_help import build_tenant_ai_help_context


class TenantAIHelpRouteGroundingTests(SimpleTestCase):
    def test_help_url_includes_focus_route(self):
        factory = RequestFactory()
        request = factory.get("/portal/")
        request.school = None
        request.user = type("U", (), {"is_authenticated": True})()
        ctx = build_tenant_ai_help_context(request, route_name="setup_studio:launch")
        self.assertEqual(ctx["route_name"], "setup_studio:launch")
        self.assertIn("help_center_url", ctx)
