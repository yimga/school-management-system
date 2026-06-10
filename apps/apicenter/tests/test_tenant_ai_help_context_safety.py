"""Tenant AI help — apicenter route grounding contract."""

from django.test import RequestFactory, TestCase

from apps.platform_runtime.tenant_ai_help import build_tenant_ai_help_context


class ApicenterTenantAIHelpContextTests(TestCase):
    def test_route_name_in_context(self):
        factory = RequestFactory()
        request = factory.get("/portal/dashboard/")
        request.school = None
        request.user = type("U", (), {"is_authenticated": False})()
        ctx = build_tenant_ai_help_context(request, route_name="accounts:backend_dashboard")
        self.assertEqual(ctx["route_name"], "accounts:backend_dashboard")
        self.assertIn("help_center_url", ctx)

    def test_breadcrumbs_include_route(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.school = None
        request.user = type("U", (), {"is_authenticated": False})()
        ctx = build_tenant_ai_help_context(request, route_name="evals:teacher_gradebook")
        self.assertTrue(any(b.get("value") == "evals:teacher_gradebook" for b in ctx["breadcrumbs"]))
