"""
Tests for Tenant Runtime Contract and compilation order.
Phase 1: runtime contract shape, strict compilation order, precedence, job helper.
"""
from django.test import TestCase

from apps.tenancy.context import TenantContext
from apps.platform_runtime.contracts import (
    TenantRuntime,
    RouteContext,
    RegistryContext,
    BlueprintContext,
    PolicyContext,
    FlagsContext,
    RuntimeDebug,
)
from apps.platform_runtime.runtime_resolver import (
    build_tenant_runtime,
    build_tenant_runtime_for_tenant,
)


class TenantRuntimeContractTests(TestCase):
    """Runtime contract shape and compilation order."""

    def test_build_tenant_runtime_with_empty_tenant_ctx(self):
        """Without tenant, runtime has route=marketing and no school."""
        ctx = TenantContext.empty(host="example.com")
        runtime = build_tenant_runtime(ctx, request=None)
        self.assertIsInstance(runtime, TenantRuntime)
        self.assertEqual(runtime.tenant_ctx, ctx)
        self.assertFalse(runtime.is_tenant)
        self.assertIsNone(runtime._school)
        self.assertEqual(runtime.policy, {})

    def test_runtime_has_all_sections_after_build(self):
        """All typed sections are present after build (may be default/stub)."""
        ctx = TenantContext(
            tenant_id="",
            schema_name=None,
            school_id=None,
            country=None,
            timezone=None,
            feature_flags={},
            policy_overrides={},
            host="example.com",
        )
        runtime = build_tenant_runtime(ctx, request=None)
        self.assertIsNotNone(runtime.route)
        self.assertIsInstance(runtime.route, RouteContext)
        self.assertIsNotNone(runtime.tenant)
        self.assertIsNotNone(runtime.registry)
        self.assertIsInstance(runtime.registry, RegistryContext)
        self.assertIsNotNone(runtime.blueprint)
        self.assertIsInstance(runtime.blueprint, BlueprintContext)
        self.assertIsNotNone(runtime.policy_typed)
        self.assertIsInstance(runtime.policy_typed, PolicyContext)
        self.assertIsNotNone(runtime.branding)
        self.assertIsNotNone(runtime.flags)
        self.assertIsInstance(runtime.flags, FlagsContext)
        self.assertIsNotNone(runtime.entitlements)
        self.assertIsNotNone(runtime.workflows)
        self.assertIsNotNone(runtime.dashboards)
        self.assertIsNotNone(runtime.integrations)
        self.assertIsNotNone(runtime.marketplace)
        self.assertIsNotNone(runtime.compliance)
        self.assertIsNotNone(runtime.locale)
        self.assertIsNotNone(runtime.security)
        self.assertIsNotNone(runtime.modules)
        self.assertIsNotNone(runtime.debug)
        self.assertIsInstance(runtime.debug, RuntimeDebug)

    def test_compilation_order_in_debug_trace(self):
        """Debug compilation_trace reflects strict order 1..13."""
        ctx = TenantContext.empty(host="test.com")
        runtime = build_tenant_runtime(ctx, request=None)
        trace = runtime.debug.compilation_trace
        self.assertIn("1:route", trace)
        self.assertIn("2:tenant", trace)
        self.assertIn("3:registry", trace)
        self.assertIn("4:blueprint", trace)
        self.assertIn("5:policy", trace)
        self.assertIn("6:flags_entitlements", trace)
        self.assertIn("7:branding", trace)
        self.assertIn("8:workflows", trace)
        self.assertIn("9:dashboards", trace)
        self.assertIn("10:integrations_marketplace", trace)
        self.assertIn("11:compliance_security", trace)
        self.assertIn("12:module_configs", trace)
        self.assertIn("13:freeze", trace)
        self.assertEqual(trace[-1], "13:freeze")

    def test_route_surface_marketing_when_not_tenant(self):
        """When tenant_ctx is not tenant, surface is marketing."""
        ctx = TenantContext.empty(host="runmycampus.com")
        runtime = build_tenant_runtime(ctx, request=None)
        self.assertEqual(runtime.route.surface, "marketing")

    def test_flags_is_enabled_default_false(self):
        """FlagsContext.is_enabled returns False for missing key."""
        ctx = TenantContext.empty(host="x.com")
        runtime = build_tenant_runtime(ctx, request=None)
        self.assertFalse(runtime.flags.is_enabled("new_gradebook"))
        # With feature_flags set on context, flag is respected
        ctx2 = TenantContext(
            tenant_id="t1", schema_name="t1", school_id=None, country=None, timezone=None,
            feature_flags={"new_gradebook": True}, policy_overrides={}, host="x.com",
        )
        runtime2 = build_tenant_runtime(ctx2, request=None)
        self.assertTrue(runtime2.flags.is_enabled("new_gradebook"))

    def test_build_tenant_runtime_for_tenant_job_mode(self):
        """build_tenant_runtime_for_tenant(tenant, mode='job') returns TenantRuntime."""
        # Pass None as tenant: should still return a runtime (empty tenant_ctx)
        runtime = build_tenant_runtime_for_tenant(None, mode="job")
        self.assertIsInstance(runtime, TenantRuntime)
        self.assertIsNotNone(runtime.debug)
        self.assertEqual(runtime.debug.applied_overrides, ["mode"])
