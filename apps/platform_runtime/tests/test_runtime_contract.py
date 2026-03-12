"""
Tests for Tenant Runtime Contract and compilation order.
Phase 1: runtime contract shape, strict compilation order, precedence, job helper.
"""
from django.test import TestCase

from apps.platform_runtime.helpers import (
    get_effective_flags_for_school,
    get_effective_site_settings,
)
from apps.platform_runtime.models import RuntimeDefaults
from apps.runtime_blueprints.models import ReportCardStyle as OwnedReportCardStyle
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
from apps.schools.models import School
from apps.siteconfig.models import SiteSettings, build_platform_default_site_settings


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

    def test_runtime_with_school_and_policy_contains_all_compilation_steps(self):
        """Runtime built with a real school and policy contains all 13 steps with real data."""
        from unittest.mock import Mock
        school = School.objects.create(
            name="Runtime Contract School",
            slug="runtime-contract-school",
            subdomain="runtime-contract-school",
            is_active=True,
            settings={
                "grading": {"pass_mark": 50, "scale": "0-100"},
                "admissions": {"numbering_strategy": "annual"},
            },
            features={"library": True},
        )
        request = Mock()
        request.school = school
        request.user = None
        tenant_ctx = TenantContext(
            tenant_id=str(school.id),
            schema_name="public",
            school_id=school.id,
            country="US",
            timezone="UTC",
            feature_flags={},
            policy_overrides={},
            host="runtime-contract-school.runmycampus.com",
        )
        runtime = build_tenant_runtime(tenant_ctx, request=request)
        self.assertIsNotNone(runtime._school)
        self.assertEqual(runtime.tenant.slug, "runtime-contract-school")
        self.assertIsNotNone(runtime.policy_typed)
        self.assertIsNotNone(runtime.policy_typed.raw)
        self.assertIsNotNone(runtime.modules)
        self.assertIsNotNone(runtime.modules.gradebook)
        self.assertIsNotNone(runtime.modules.admissions)
        self.assertIn("1:route", runtime.debug.compilation_trace)
        self.assertIn("13:freeze", runtime.debug.compilation_trace)
        self.assertEqual(len(runtime.debug.compilation_trace), 13)
        school.delete()

    def test_build_tenant_runtime_for_tenant_job_mode(self):
        """build_tenant_runtime_for_tenant(tenant, mode='job') returns TenantRuntime."""
        # Pass None as tenant: should still return a runtime (empty tenant_ctx)
        runtime = build_tenant_runtime_for_tenant(None, mode="job")
        self.assertIsInstance(runtime, TenantRuntime)
        self.assertIsNotNone(runtime.debug)
        self.assertEqual(runtime.debug.applied_overrides, ["mode"])


class RuntimeHelperResolutionTests(TestCase):
    def test_site_settings_owned_payload_filters_to_requested_owner(self):
        site = SiteSettings.get_solo()
        site.site_name = "Brand Surface"
        site.backend_feature_flags = {"enable_api_center": True}
        site.default_dashboard_view = "ACADEMICS"
        site.save(update_fields=["site_name", "backend_feature_flags", "default_dashboard_view"])

        brand_payload = site.owned_payload("brand_experience")
        runtime_payload = site.owned_payload("runtime_blueprints")
        policy_payload = site.owned_payload("policies_rules")

        self.assertEqual(brand_payload["site_name"], "Brand Surface")
        self.assertIn("default_dashboard_view", runtime_payload)
        self.assertNotIn("site_name", runtime_payload)
        self.assertEqual(policy_payload["backend_feature_flags"]["enable_api_center"], True)

    def test_runtime_defaults_sync_from_site_settings_can_scope_to_owner_domains(self):
        site = SiteSettings.get_solo()
        site.site_name = "Scoped Brand"
        site.default_dashboard_view = "ACADEMICS"
        site.backend_feature_flags = {"enable_api_center": True}
        site.save(update_fields=["site_name", "default_dashboard_view", "backend_feature_flags"])
        RuntimeDefaults.objects.all().delete()

        runtime_defaults, _created = RuntimeDefaults.sync_from_site_settings(
            site,
            owners=("runtime_blueprints", "policies_rules"),
        )

        self.assertIn("default_dashboard_view", runtime_defaults.payload)
        self.assertIn("backend_feature_flags", runtime_defaults.payload)
        self.assertNotIn("site_name", runtime_defaults.payload)

    def test_runtime_defaults_scoped_sync_preserves_other_owner_domains(self):
        site = SiteSettings.get_solo()
        site.site_name = "Brand Baseline"
        site.default_dashboard_view = "OVERVIEW"
        site.backend_feature_flags = {"enable_api_center": False}
        site.save(update_fields=["site_name", "default_dashboard_view", "backend_feature_flags"])

        RuntimeDefaults.objects.update_or_create(
            pk=1,
            defaults={
                "payload": {
                    "site_name": "Brand Baseline",
                    "default_dashboard_view": "OVERVIEW",
                    "backend_feature_flags": {"enable_api_center": False},
                }
            },
        )

        site.backend_feature_flags = {"enable_api_center": True}
        runtime_defaults, _created = RuntimeDefaults.sync_from_site_settings(
            site,
            owners=("policies_rules",),
        )

        self.assertEqual(runtime_defaults.payload["site_name"], "Brand Baseline")
        self.assertEqual(runtime_defaults.payload["default_dashboard_view"], "OVERVIEW")
        self.assertEqual(runtime_defaults.payload["backend_feature_flags"]["enable_api_center"], True)

    def test_site_settings_save_auto_syncs_runtime_defaults_for_changed_owner_domains(self):
        site = SiteSettings.get_solo()
        RuntimeDefaults.objects.all().delete()

        site.site_name = "Auto Synced Brand"
        site.backend_feature_flags = {"enable_api_center": True}
        site.maintenance_mode = True
        site.save(update_fields=["site_name", "backend_feature_flags", "maintenance_mode"])

        runtime_defaults = RuntimeDefaults.get_singleton()

        self.assertIsNotNone(runtime_defaults)
        self.assertEqual(runtime_defaults.payload["site_name"], "Auto Synced Brand")
        self.assertEqual(runtime_defaults.payload["backend_feature_flags"]["enable_api_center"], True)
        self.assertNotIn("maintenance_mode", runtime_defaults.payload)

    def test_site_settings_resolve_default_report_style_uses_owner_surface(self):
        style = OwnedReportCardStyle.objects.create(
            slug="runtime-owned-style",
            name="Runtime Owned Style",
            term_template="reports/term_report_cameroon_modern.html",
            annual_template="reports/annual_report_cameroon_modern.html",
            primary_color="#0d173b",
            accent_color="#007bff",
            is_active=True,
        )
        site = SiteSettings.get_solo()
        site.default_term_report_style_id = style.pk
        site.save(update_fields=["default_term_report_style"])

        resolved = site.resolve_default_report_style("TERM")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, style.pk)
        self.assertEqual(resolved._meta.app_label, "runtime_blueprints")

    def test_get_effective_site_settings_prefers_runtime_defaults_over_legacy_singleton(self):
        site = SiteSettings.get_solo()
        site.site_name = "Legacy Site Settings"
        site.enable_offline_mode = False
        site.save(update_fields=["site_name", "enable_offline_mode"])

        RuntimeDefaults.objects.update_or_create(
            pk=1,
            defaults={
                "payload": {
                    "site_name": "Runtime Defaults Platform",
                    "enable_offline_mode": True,
                }
            },
        )

        resolved = get_effective_site_settings()

        self.assertEqual(resolved.site_name, "Runtime Defaults Platform")
        self.assertTrue(resolved.enable_offline_mode)
        self.assertEqual(resolved.pk, site.pk)

    def test_get_effective_site_settings_uses_school_overrides(self):
        site = SiteSettings.get_solo()
        site.site_name = "Platform Default"
        site.enable_offline_mode = False
        site.save(update_fields=["site_name", "enable_offline_mode"])

        school = School.objects.create(
            name="Tenant Override Academy",
            slug="tenant-override-academy",
            subdomain="tenant-override-academy",
            is_active=True,
            settings={
                "site_name": "Tenant Override Academy Portal",
                "enable_offline_mode": True,
            },
        )

        resolved = get_effective_site_settings(school=school)

        self.assertEqual(resolved.site_name, "Tenant Override Academy Portal")
        self.assertTrue(resolved.enable_offline_mode)
        self.assertEqual(site.site_name, "Platform Default")
        self.assertFalse(site.enable_offline_mode)

    def test_get_effective_flags_for_school_merges_school_backend_flags(self):
        site = SiteSettings.get_solo()
        site.backend_feature_flags = {"enable_api_center": False, "require_guardian_finance_opt_in": False}
        site.save(update_fields=["backend_feature_flags"])

        school = School.objects.create(
            name="Flag Override Academy",
            slug="flag-override-academy",
            subdomain="flag-override-academy",
            is_active=True,
            settings={"backend_feature_flags": {"enable_api_center": True}},
        )

        flags = get_effective_flags_for_school(school)

        self.assertTrue(flags["enable_api_center"])
        self.assertFalse(flags["require_guardian_finance_opt_in"])

    def test_site_settings_get_backend_feature_flags_merges_defaults(self):
        site = SiteSettings.get_solo()
        site.backend_feature_flags = {"enable_api_center": True}
        site.save(update_fields=["backend_feature_flags"])

        flags = site.get_backend_feature_flags()

        self.assertTrue(flags["enable_api_center"])
        self.assertIn("backend_module_overview", flags)

    def test_site_settings_owner_accessors_expose_brand_and_report_preview_payloads(self):
        site = SiteSettings.get_solo()
        site.site_name = "North Star Academy"
        site.school_code = "NSA"
        site.country = "Cameroon"
        site.region = "Centre"
        site.ministry = "Education"
        site.tagline = "One platform"
        site.report_preview_contact_email = "reports@example.com"
        site.report_preview_contact_phone = "+237600000000"
        site.report_preview_footer_note = "Preview footer"
        site.default_report_preview_type = "ANNUAL"
        site.save(
            update_fields=[
                "site_name",
                "school_code",
                "country",
                "region",
                "ministry",
                "tagline",
                "report_preview_contact_email",
                "report_preview_contact_phone",
                "report_preview_footer_note",
                "default_report_preview_type",
            ]
        )

        brand_metadata = site.get_brand_metadata()
        preview_settings = site.get_report_preview_settings()

        self.assertEqual(brand_metadata["school_name"], "North Star Academy")
        self.assertEqual(brand_metadata["school_code"], "NSA")
        self.assertEqual(brand_metadata["country"], "Cameroon")
        self.assertEqual(brand_metadata["region"], "Centre")
        self.assertEqual(brand_metadata["ministry"], "Education")
        self.assertEqual(brand_metadata["tagline"], "One platform")
        self.assertEqual(preview_settings["contact_email"], "reports@example.com")
        self.assertEqual(preview_settings["contact_phone"], "+237600000000")
        self.assertEqual(preview_settings["footer_note"], "Preview footer")
        self.assertEqual(preview_settings["default_report_type"], "ANNUAL")

    def test_build_platform_default_site_settings_returns_unsaved_compat_shape(self):
        site = build_platform_default_site_settings()

        self.assertEqual(site.pk, 1)
        self.assertTrue(site._state.adding)
        self.assertIsInstance(site.get_preview_platform_config(), dict)


class IntegrationGovernanceTests(TestCase):
    """Provider registry: runtime step 10 uses ServiceIntegration; catalog is source of keys."""

    def test_integrations_context_shape_from_step10(self):
        """Step 10 populates integrations with payment_provider, messaging_provider, enabled_providers."""
        ctx = TenantContext.empty(host="example.com")
        runtime = build_tenant_runtime(ctx, request=None)
        self.assertIsNotNone(runtime.integrations)
        self.assertIsInstance(runtime.integrations.enabled_providers, list)
        self.assertIsInstance(runtime.integrations.messaging_channels, list)

    def test_integration_catalog_keys_non_empty(self):
        """INTEGRATION_CATALOG defines at least one key; API Center and resolve_* use these keys."""
        from apps.siteconfig.integration_catalog import INTEGRATION_CATALOG, list_catalog_keys
        keys = list_catalog_keys()
        self.assertGreater(len(keys), 0)
        for k in keys:
            self.assertIn(k, INTEGRATION_CATALOG)
            entry = INTEGRATION_CATALOG[k]
            self.assertIn("label", entry)
            self.assertIn("config_schema", entry)
