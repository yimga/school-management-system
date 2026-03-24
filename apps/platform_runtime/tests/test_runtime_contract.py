"""
Tests for Tenant Runtime Contract and compilation order.
Phase 1: runtime contract shape, strict compilation order, precedence, job helper.
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.platform_runtime.helpers import (
    get_effective_feature_control_settings,
    get_effective_flags_for_school,
    get_effective_offline_runtime_settings,
    get_effective_site_settings,
    get_effective_support_contact_settings,
    get_platform_site_settings_record,
)
from apps.platform_runtime.models import RuntimeDefaults
from apps.runtime_blueprints.models import ReportCardStyle as OwnedReportCardStyle
from apps.brand_experience.models import ThemePack
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
from apps.platform_runtime.precedence import PRECEDENCE_ORDER
from apps.platform_runtime.runtime_resolver import _step4_blueprint
from apps.platform_runtime.runtime_inspector import inspect_runtime
from apps.platform_runtime.runtime_resolver import (
    build_tenant_runtime,
    build_tenant_runtime_for_tenant,
)
from apps.schools.models import School
from apps.siteconfig.models import SiteSettings, build_platform_default_site_settings


def _persist_runtime_test_state(**payload_updates: object) -> None:
    """Phase B: behavioral keys live in RuntimeDefaults.payload, not SiteSettings columns."""
    from apps.platform_runtime.helpers import invalidate_effective_site_settings_cache

    SiteSettings._persist_runtime_payload_updates(payload_updates)
    invalidate_effective_site_settings_cache()


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

    def test_step4_blueprint_uses_tenant_blueprint_accessor(self):
        """Regression: reverse accessor is tenant_blueprint (related_name), not tenantblueprint."""

        class _Pack:
            id = 42
            slug = "fixture-pack"
            code = "fixture-pack"
            category = "K12"
            default_dashboard_pack_id = 7
            default_workflow_pack_id = 8
            country_code = ""

        class _TB:
            applied_pack = _Pack()

        class _School:
            tenant_blueprint = _TB()

        school = _School()
        blueprint = _step4_blueprint(school, {})
        self.assertEqual(blueprint.id, 42)
        self.assertEqual(blueprint.code, "fixture-pack")
        self.assertEqual(blueprint.default_dashboard_pack, 7)

    def test_flags_is_enabled_default_false(self):
        """FlagsContext.is_enabled returns False for missing key."""
        ctx = TenantContext.empty(host="x.com")
        runtime = build_tenant_runtime(ctx, request=None)
        self.assertFalse(runtime.flags.is_enabled("new_gradebook"))
        # With feature_flags set on context, flag is respected
        ctx2 = TenantContext(
            tenant_id="t1",
            schema_name="t1",
            school_id=None,
            country=None,
            timezone=None,
            feature_flags={"new_gradebook": True},
            policy_overrides={},
            host="x.com",
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
        from apps.platform_runtime.tracing import get_runtime_trace_id

        self.assertIsNotNone(get_runtime_trace_id(request))
        self.assertEqual(len(get_runtime_trace_id(request) or ""), 16)
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

    def test_runtime_tenant_identity_includes_primary_sector(self):
        """Wedges 14–22: When school has primary_sector, runtime.tenant.primary_sector is set for RBAC/config."""
        school = School.objects.create(
            name="Sector School",
            slug="sector-school",
            subdomain="sector-school",
            is_active=True,
            primary_sector="PUBLIC",
        )
        tenant_ctx = TenantContext(
            tenant_id=str(school.id),
            schema_name="public",
            school_id=school.id,
            country="US",
            timezone="UTC",
            feature_flags={},
            policy_overrides={},
            host="sector-school.runmycampus.com",
        )
        runtime = build_tenant_runtime(tenant_ctx, request=None, school=school)
        self.assertEqual(runtime.tenant.primary_sector, "PUBLIC")
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
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            site_name="Brand Surface",
            backend_feature_flags={"enable_api_center": True},
            default_dashboard_view="ACADEMICS",
        )
        site.refresh_from_db()

        brand_payload = site.owned_payload("brand_experience")
        runtime_payload = site.owned_payload("runtime_blueprints")
        policy_payload = site.owned_payload("policies_rules")

        self.assertEqual(brand_payload["site_name"], "Brand Surface")
        self.assertIn("default_dashboard_view", runtime_payload)
        self.assertNotIn("site_name", runtime_payload)
        self.assertEqual(
            policy_payload["backend_feature_flags"]["enable_api_center"], True
        )

    def test_runtime_defaults_sync_from_site_settings_can_scope_to_owner_domains(self):
        """Scoped sync writes only requested owners; omit brand keys from the slice under test."""
        site = get_platform_site_settings_record(create=True)
        RuntimeDefaults.objects.all().delete()
        _persist_runtime_test_state(
            default_dashboard_view="ACADEMICS",
            backend_feature_flags={"enable_api_center": True},
        )
        site.refresh_from_db()

        runtime_defaults, _created = RuntimeDefaults.sync_from_site_settings(
            site,
            owners=("runtime_blueprints", "policies_rules"),
        )

        self.assertIn("default_dashboard_view", runtime_defaults.payload)
        self.assertIn("backend_feature_flags", runtime_defaults.payload)
        self.assertNotIn("site_name", runtime_defaults.payload)

    def test_backfill_runtime_defaults_command_creates_platform_payload(self):
        site = get_platform_site_settings_record(create=True)
        RuntimeDefaults.objects.all().delete()
        _persist_runtime_test_state(
            site_name="Command Synced Platform",
            enable_offline_mode=True,
        )
        site.refresh_from_db()

        stdout = StringIO()
        call_command("backfill_runtime_defaults", stdout=stdout)

        runtime_defaults = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(runtime_defaults)
        self.assertEqual(
            runtime_defaults.payload["site_name"], "Command Synced Platform"
        )
        self.assertTrue(runtime_defaults.payload["enable_offline_mode"])
        out = stdout.getvalue().lower()
        self.assertTrue(
            "created" in out or "updated" in out,
            msg="backfill command should report created or updated",
        )

    def test_runtime_defaults_scoped_sync_preserves_other_owner_domains(self):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            site_name="Brand Baseline",
            default_dashboard_view="OVERVIEW",
            backend_feature_flags={"enable_api_center": False},
        )
        site.refresh_from_db()

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

        _persist_runtime_test_state(
            backend_feature_flags={"enable_api_center": True},
        )
        site.refresh_from_db()
        runtime_defaults, _created = RuntimeDefaults.sync_from_site_settings(
            site,
            owners=("policies_rules",),
        )

        self.assertEqual(runtime_defaults.payload["site_name"], "Brand Baseline")
        self.assertEqual(runtime_defaults.payload["default_dashboard_view"], "OVERVIEW")
        self.assertEqual(
            runtime_defaults.payload["backend_feature_flags"]["enable_api_center"], True
        )

    def test_site_settings_save_auto_syncs_runtime_defaults_for_changed_owner_domains(
        self,
    ):
        """Phase B: virtual keys live in RuntimeDefaults; DB save syncs only concrete owners."""
        site = get_platform_site_settings_record(create=True)
        RuntimeDefaults.objects.all().delete()
        _persist_runtime_test_state(
            site_name="Auto Synced Brand",
            backend_feature_flags={"enable_api_center": True},
        )
        site.maintenance_mode = True
        site.save(update_fields=["maintenance_mode"])
        site.refresh_from_db()

        runtime_defaults = RuntimeDefaults.get_singleton()

        self.assertIsNotNone(runtime_defaults)
        self.assertEqual(runtime_defaults.payload["site_name"], "Auto Synced Brand")
        self.assertEqual(
            runtime_defaults.payload["backend_feature_flags"]["enable_api_center"], True
        )
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
        site = get_platform_site_settings_record(create=True)
        site.apply_theme_experience_state(
            field_updates={"default_term_report_style": style},
            save=True,
        )

        resolved = site.resolve_default_report_style("TERM")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, style.pk)
        self.assertEqual(resolved._meta.app_label, "runtime_blueprints")

    def test_get_effective_site_settings_prefers_runtime_defaults_over_legacy_singleton(
        self,
    ):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            site_name="Legacy Site Settings",
            enable_offline_mode=False,
        )
        site.refresh_from_db()

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
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            site_name="Platform Default",
            enable_offline_mode=False,
        )
        site.refresh_from_db()

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
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            backend_feature_flags={
                "enable_api_center": False,
                "require_guardian_finance_opt_in": False,
            },
        )
        site.refresh_from_db()

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
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            backend_feature_flags={"enable_api_center": True},
        )
        site.refresh_from_db()

        flags = site.get_backend_feature_flags()

        self.assertTrue(flags["enable_api_center"])
        self.assertIn("backend_module_overview", flags)

    def test_site_settings_feature_control_settings_use_owner_surfaces(self):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            portal_features={"documents": True},
            backend_feature_flags={"enable_api_center": True},
            notification_channels=["email", "sms"],
            enable_parent_portal=True,
            preview_mode_enabled=True,
            show_header_search=True,
            report_downloads_enabled=False,
            auto_tag_photos_from_exif=True,
        )
        site.refresh_from_db()
        site.maintenance_mode = True
        site.save(update_fields=["maintenance_mode"])

        feature_settings = site.get_feature_control_settings()

        self.assertTrue(feature_settings["portal_features"]["documents"])
        self.assertTrue(feature_settings["backend_feature_flags"]["enable_api_center"])
        self.assertEqual(feature_settings["notification_channels"], ["email", "sms"])
        self.assertTrue(feature_settings["enable_parent_portal"])
        self.assertTrue(feature_settings["maintenance_mode"])
        self.assertTrue(feature_settings["preview_mode_enabled"])
        self.assertTrue(feature_settings["show_header_search"])
        self.assertFalse(feature_settings["report_downloads_enabled"])
        self.assertTrue(feature_settings["auto_tag_photos_from_exif"])

    def test_site_settings_notification_delivery_settings_use_owner_surfaces(self):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            notification_channels=["email", "sms"],
            email_from_address="northstar@example.com",
        )
        site.refresh_from_db()

        delivery_settings = site.get_notification_delivery_settings()

        self.assertEqual(delivery_settings["notification_channels"], ["email", "sms"])
        self.assertEqual(
            delivery_settings["email_from_address"], "northstar@example.com"
        )

    def test_site_settings_offline_runtime_settings_use_owner_surfaces(self):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            enable_offline_mode=True,
            offline_sync_conflict_resolution="auto_merge",
            backend_feature_flags={"enable_offline_attendance_sync": False},
        )
        site.refresh_from_db()

        offline_settings = site.get_offline_runtime_settings()

        self.assertTrue(offline_settings["enable_offline_mode"])
        self.assertEqual(
            offline_settings["offline_sync_conflict_resolution"],
            "auto_merge",
        )
        self.assertFalse(
            offline_settings["backend_feature_flags"]["enable_offline_attendance_sync"]
        )

    def test_request_helpers_use_owner_scoped_site_accessors(self):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            portal_features={"documents": True},
            enable_offline_mode=True,
            whatsapp_support_number="+15550001111",
        )
        site.refresh_from_db()

        feature_settings = get_effective_feature_control_settings()
        offline_settings = get_effective_offline_runtime_settings()
        support_settings = get_effective_support_contact_settings()

        self.assertTrue(feature_settings["portal_features"]["documents"])
        self.assertTrue(offline_settings["enable_offline_mode"])
        self.assertEqual(
            support_settings["whatsapp_support_number"],
            "+15550001111",
        )

    def test_site_settings_owner_accessors_expose_brand_and_report_preview_payloads(
        self,
    ):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            site_name="North Star Academy",
            school_code="NSA",
            country="Cameroon",
            region="Centre",
            ministry="Education",
            tagline="One platform",
            report_preview_contact_email="reports@example.com",
            report_preview_contact_phone="+237600000000",
            report_preview_footer_note="Preview footer",
            default_report_preview_type="ANNUAL",
        )
        site.refresh_from_db()

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

    def test_site_settings_theme_selection_ids_use_brand_owner_payload(self):
        portal_pack = ThemePack.objects.create(
            name="Portal Pack",
            slug="portal-pack-runtime-contract",
            is_active=True,
        )
        admin_pack = ThemePack.objects.create(
            name="Admin Pack",
            slug="admin-pack-runtime-contract",
            is_active=True,
            applies_to_admin=True,
        )
        teacher_pack = ThemePack.objects.create(
            name="Teacher Pack",
            slug="teacher-pack-runtime-contract",
            is_active=True,
        )
        parent_pack = ThemePack.objects.create(
            name="Parent Pack",
            slug="parent-pack-runtime-contract",
            is_active=True,
        )
        site = get_platform_site_settings_record(create=True)
        site.apply_theme_experience_state(
            field_updates={
                "theme_pack": portal_pack,
                "admin_theme_pack": admin_pack,
                "teacher_theme_pack": teacher_pack,
                "parent_theme_pack": parent_pack,
            },
            save=True,
        )

        theme_selection_ids = site.get_theme_selection_ids()

        self.assertEqual(theme_selection_ids["theme_pack_id"], portal_pack.pk)
        self.assertEqual(theme_selection_ids["admin_theme_pack_id"], admin_pack.pk)
        self.assertEqual(theme_selection_ids["teacher_theme_pack_id"], teacher_pack.pk)
        self.assertEqual(theme_selection_ids["parent_theme_pack_id"], parent_pack.pk)

    def test_site_settings_theme_experience_settings_use_owner_surfaces(self):
        portal_pack = ThemePack.objects.create(
            name="Owner Portal Pack",
            slug="owner-portal-pack-runtime-contract",
            is_active=True,
        )
        admin_pack = ThemePack.objects.create(
            name="Owner Admin Pack",
            slug="owner-admin-pack-runtime-contract",
            is_active=True,
            applies_to_admin=True,
        )
        site = get_platform_site_settings_record(create=True)
        site.apply_theme_experience_state(
            field_updates={
                "theme_pack": portal_pack,
                "admin_theme_pack": admin_pack,
            },
            save=True,
        )
        _persist_runtime_test_state(
            primary_color="#112233",
            accent_color="#445566",
            use_dark_mode=True,
            skip_theme_publish_guard=True,
            default_dashboard_view="ACADEMICS",
            default_refresh_rate=90,
            report_downloads_enabled=False,
        )
        site.refresh_from_db()

        settings = site.get_theme_experience_settings()

        self.assertEqual(settings["primary_color"], "#112233")
        self.assertEqual(settings["accent_color"], "#445566")
        self.assertTrue(settings["use_dark_mode"])
        self.assertTrue(settings["skip_theme_publish_guard"])
        self.assertEqual(settings["theme_pack_id"], portal_pack.pk)
        self.assertEqual(settings["admin_theme_pack_id"], admin_pack.pk)
        self.assertEqual(settings["default_dashboard_view"], "ACADEMICS")
        self.assertEqual(settings["default_refresh_rate"], 90)
        self.assertFalse(settings["report_downloads_enabled"])

    def test_site_settings_owner_accessors_normalize_legacy_placeholders(self):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            site_name="School System",
            school_code="GIL",
            tagline="Knowledge ƒ?› Technology ƒ?› Excellence",
            report_preview_contact_email="reports@gileadtech.edu",
            report_preview_contact_phone="+237 670 000 000",
        )
        site.refresh_from_db()

        brand_metadata = site.get_brand_metadata()
        preview_settings = site.get_report_preview_settings()

        self.assertEqual(brand_metadata["school_name"], "RunMyCampus")
        self.assertEqual(brand_metadata["school_code"], "RMC")
        self.assertEqual(
            brand_metadata["tagline"], "Education management for every school."
        )
        self.assertEqual(preview_settings["contact_email"], "support@runmycampus.com")
        self.assertEqual(preview_settings["contact_phone"], "")

    def test_site_settings_finance_runtime_config_uses_policy_owner_payload(self):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            finance_auto_generate_invoices_enabled=True,
            finance_auto_generate_schedule={
                "mode": "term_start",
                "term_start_offset_days": 5,
            },
            finance_fee_plan_auto_copy_mode="year_end",
            finance_invoice_overdue_grace_period_days=4,
            finance_receipt_amount_tolerance=Decimal("2.50"),
            finance_bank_verification_auto_approve=True,
            finance_reminder_no_contact_action="create_task",
        )
        site.refresh_from_db()

        finance_settings = site.get_finance_runtime_config()

        self.assertTrue(finance_settings["auto_generate_invoices_enabled"])
        self.assertEqual(
            finance_settings["auto_generate_schedule"]["mode"], "term_start"
        )
        self.assertEqual(finance_settings["fee_plan_auto_copy_mode"], "year_end")
        self.assertEqual(finance_settings["invoice_overdue_grace_period_days"], 4)
        self.assertEqual(finance_settings["receipt_amount_tolerance"], Decimal("2.50"))
        self.assertTrue(finance_settings["bank_verification_auto_approve"])
        self.assertEqual(finance_settings["reminder_no_contact_action"], "create_task")

    def test_site_settings_marketplace_integration_settings_use_owner_payload(self):
        site = get_platform_site_settings_record(create=True)
        _persist_runtime_test_state(
            marksheet_ocr_command="/opt/runmycampus/bin/tesseract",
            sms_sender_id="RUNMYCAMPUS",
            email_from_address="platform@runmycampus.com",
            whatsapp_support_number="+15551234567",
        )
        site.refresh_from_db()

        integration_settings = site.get_marketplace_integration_settings()

        self.assertEqual(
            integration_settings["marksheet_ocr_command"],
            "/opt/runmycampus/bin/tesseract",
        )
        self.assertEqual(integration_settings["sms_sender_id"], "RUNMYCAMPUS")
        self.assertEqual(
            integration_settings["email_from_address"], "platform@runmycampus.com"
        )
        self.assertEqual(
            integration_settings["whatsapp_support_number"], "+15551234567"
        )

    def test_build_platform_default_site_settings_returns_unsaved_compat_shape(self):
        site = build_platform_default_site_settings()

        self.assertEqual(site.pk, 1)
        self.assertTrue(site._state.adding)
        self.assertEqual(site.site_name, "RunMyCampus")
        self.assertEqual(site.school_code, "RMC")
        self.assertIsInstance(site.get_preview_platform_config(), dict)


class RuntimeInspectorPrecedenceTests(TestCase):
    """Phase 6: inspector exposes the same seven-level precedence chain as precedence.py."""

    def test_inspect_runtime_includes_precedence_chain_matching_precedence_order(self):
        ctx = TenantContext.empty(host="inspector.example.com")
        runtime = build_tenant_runtime(ctx, request=None)
        payload = inspect_runtime(runtime)
        chain = payload.get("precedence_chain") or []
        keys = [entry["key"] for entry in chain]
        self.assertEqual(keys, list(PRECEDENCE_ORDER))
        self.assertEqual(len(chain), 7)
        self.assertEqual(chain[0]["key"], "platform_default")
        self.assertEqual(chain[-1]["key"], "sandbox_override")
        self.assertEqual(
            payload.get("feature_flags_merge_order"),
            ["policy_bundle", "tenant_override", "sandbox_override"],
        )
        self.assertIn("entitlement_registry", payload)
        self.assertEqual(payload["entitlement_registry"]["registry_schema_version"], 1)
        self.assertIn("blueprint_lifecycle", payload)
        self.assertIn("marketplace_install_registry", payload)


class ResolverRegistryContractTests(TestCase):
    """NEXT_50 step 20: resolver_registry entry points are declared and importable."""

    def test_resolver_registry_entry_points_non_empty(self):
        """RESOLVER_ENTRY_POINTS is the single source of truth; must be non-empty and well-formed."""
        from apps.platform_runtime.resolver_registry import RESOLVER_ENTRY_POINTS

        self.assertIsInstance(RESOLVER_ENTRY_POINTS, list)
        self.assertGreater(len(RESOLVER_ENTRY_POINTS), 0)
        for entry in RESOLVER_ENTRY_POINTS:
            self.assertIsInstance(
                entry, (list, tuple), f"Entry {entry!r} must be (name, location)"
            )
            self.assertEqual(len(entry), 2)
            name, location = entry
            self.assertIsInstance(name, str)
            self.assertIsInstance(location, str)
            self.assertTrue(name.strip(), f"Resolver name must be non-empty: {entry!r}")
            self.assertTrue(
                location.strip(), f"Resolver location must be non-empty: {entry!r}"
            )

    def test_resolver_registry_dotted_paths_importable(self):
        """Any entry point that is a dotted Python path must be importable (catches typos in registry)."""
        import importlib

        from apps.platform_runtime.resolver_registry import RESOLVER_ENTRY_POINTS

        for name, location in RESOLVER_ENTRY_POINTS:
            loc = location.strip()
            if " " in loc or "(" in loc:
                loc = loc.split(" ")[0].split("(")[0].strip()
            if not loc or len(loc.split(".")) < 2:
                continue
            # Require dotted path with only alnum/underscore/dots
            if not all(p.replace("_", "").isalnum() for p in loc.split(".")):
                continue
            parts = loc.split(".")
            # First try full path as module (e.g. apps.metadata.services)
            try:
                importlib.import_module(loc)
                continue
            except ImportError:
                pass
            # Else require module to have the last part as attr (e.g. ...runtime_resolver._step6_flags_entitlements)
            mod_path = ".".join(parts[:-1])
            attr_name = parts[-1]
            try:
                mod = importlib.import_module(mod_path)
                self.assertTrue(
                    hasattr(mod, attr_name),
                    f"Resolver {name!r} location {location!r}: module {mod_path} has no attr {attr_name!r}",
                )
            except ImportError as e:
                self.fail(
                    f"Resolver {name!r} location {location!r} not importable: {e}"
                )


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
        from apps.siteconfig.integration_catalog import (
            INTEGRATION_CATALOG,
            list_catalog_keys,
        )

        keys = list_catalog_keys()
        self.assertGreater(len(keys), 0)
        for k in keys:
            self.assertIn(k, INTEGRATION_CATALOG)
            entry = INTEGRATION_CATALOG[k]
            self.assertIn("label", entry)
            self.assertIn("config_schema", entry)
