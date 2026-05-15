"""
C4: Runtime and tenant-isolation tests. C5: Tenant identity on every request.
"""

from django.test import TestCase
from django.http import HttpRequest

from apps.platform_runtime.middleware import TenantRuntimeMiddleware
from apps.platform_runtime.precedence import PRECEDENCE_ORDER, precedence_rank
from apps.platform_runtime.runtime_resolver import build_tenant_runtime
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

    def test_distinct_schools_distinct_runtime_tenant_identity(self):
        """Phase 6 isolation: runtime.tenant.slug is stable per school (no cross-tenant bleed)."""
        s1 = School.objects.create(
            name="Iso School A",
            slug="iso-school-a",
            subdomain="iso-school-a",
            is_active=True,
        )
        s2 = School.objects.create(
            name="Iso School B",
            slug="iso-school-b",
            subdomain="iso-school-b",
            is_active=True,
        )
        for school, expected_slug in ((s1, "iso-school-a"), (s2, "iso-school-b")):
            ctx = TenantContext(
                tenant_id=str(school.id),
                schema_name="public",
                school_id=school.id,
                country="US",
                timezone="UTC",
                feature_flags={},
                policy_overrides={},
                host=f"{expected_slug}.example.com",
            )
            runtime = build_tenant_runtime(ctx, request=None, school=school)
            self.assertEqual(runtime.tenant.slug, expected_slug)
            self.assertEqual(runtime.tenant_ctx.school_id, school.id)

    def test_sandbox_preview_overlay_wins_on_feature_flags_in_step6(self):
        """Sandbox/preview policy_overrides feature_flags beat TenantContext.feature_flags."""
        school = School.objects.create(
            name="Sandbox Flag School",
            slug="sandbox-flag-school",
            subdomain="sandbox-flag-school",
            is_active=True,
        )
        ctx = TenantContext(
            tenant_id=str(school.id),
            schema_name="public",
            school_id=school.id,
            country="US",
            timezone="UTC",
            feature_flags={"beta_ui": False},
            policy_overrides={
                "sandbox": True,
                "feature_flags": {"beta_ui": True},
            },
            host="sandbox-flag-school.example.com",
        )
        runtime = build_tenant_runtime(
            ctx,
            request=None,
            school=school,
            policy={"features": {"beta_ui": False}},
        )
        self.assertTrue(runtime.flags.is_enabled("beta_ui"))
        self.assertTrue(runtime.route.is_sandbox)

    def test_preview_overlay_same_as_sandbox_for_feature_flags(self):
        school = School.objects.create(
            name="Preview Flag School",
            slug="preview-flag-school",
            subdomain="preview-flag-school",
            is_active=True,
        )
        ctx = TenantContext(
            tenant_id=str(school.id),
            schema_name="public",
            school_id=school.id,
            country="US",
            timezone="UTC",
            feature_flags={"beta_ui": False},
            policy_overrides={
                "preview": True,
                "sandbox_feature_flags": {"beta_ui": True},
            },
            host="preview-flag-school.example.com",
        )
        runtime = build_tenant_runtime(
            ctx,
            request=None,
            school=school,
            policy={"features": {}},
        )
        self.assertTrue(runtime.route.is_preview)
        self.assertTrue(runtime.flags.is_enabled("beta_ui"))
