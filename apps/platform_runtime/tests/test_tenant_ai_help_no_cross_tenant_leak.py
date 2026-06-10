"""Tenant AI help — no cross-tenant leakage."""

from django.test import RequestFactory, SimpleTestCase

from apps.platform_runtime.tenant_ai_help import build_tenant_ai_help_context


class TenantAIHelpNoCrossTenantLeakTests(SimpleTestCase):
    def test_tenant_hash_only_no_slug(self):
        factory = RequestFactory()
        request = factory.get("/")
        school = type("S", (), {"tenant_hash": "abc123def456", "slug": "secret-slug"})()
        request.school = school
        request.user = type("U", (), {"is_authenticated": True})()
        ctx = build_tenant_ai_help_context(request, route_name="portal:dashboard")
        blob = str(ctx)
        self.assertNotIn("secret-slug", blob)
        self.assertIn("abc123def456"[:12], ctx["tenant_id_hash"])
