"""
C4: Runtime and tenant-isolation tests. C5: Tenant identity on every request.
"""
from django.test import TestCase
from django.http import HttpRequest

from apps.platform_runtime.middleware import TenantRuntimeMiddleware
from apps.platform_runtime.precedence import PRECEDENCE_ORDER, precedence_rank
from apps.schools.models import School
from apps.tenancy.context import TenantContext


class TenantIdentityTests(TestCase):
    """C5: Assert tenant identity is set when tenant context is present."""

    def test_tenant_runtime_set_when_tenant_ctx_and_school_present(self):
        school = School.objects.create(
            name="Identity Test School",
            slug="identity-test-school",
            subdomain="identity-test-school",
            is_active=True,
        )
        middleware = TenantRuntimeMiddleware(lambda r: None)
        request = HttpRequest()
        request.school = school
        request.tenant_ctx = TenantContext(
            tenant_id=str(school.id),
            schema_name=None,
            school_id=school.id,
            country=None,
            timezone=None,
            feature_flags={},
            policy_overrides={},
            host="identity-test-school.example.com",
        )
        middleware.process_request(request)
        self.assertIsNotNone(getattr(request, "tenant_runtime", None))
        self.assertEqual(request.tenant_runtime.tenant.slug, "identity-test-school")

    def test_tenant_runtime_none_when_no_tenant_ctx(self):
        middleware = TenantRuntimeMiddleware(lambda r: None)
        request = HttpRequest()
        request.tenant_ctx = None
        middleware.process_request(request)
        self.assertIsNone(getattr(request, "tenant_runtime", None))


class TenantIsolationPrecedenceTests(TestCase):
    """C4: Precedence chain supports tenant isolation (platform < tenant < sandbox)."""

    def test_tenant_overrides_platform_in_precedence(self):
        self.assertLess(precedence_rank("platform"), precedence_rank("tenant"))
        self.assertLess(precedence_rank("tenant"), precedence_rank("sandbox"))

    def test_precedence_order_has_seven_levels(self):
        self.assertEqual(len(PRECEDENCE_ORDER), 7)
