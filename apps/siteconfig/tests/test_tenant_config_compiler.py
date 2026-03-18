from django.test import TestCase
from django.utils import timezone

from apps.siteconfig.models import (
    RegionConfig,
    EducationSystemProfile,
    SystemFeature,
    TenantSystem,
    Plan,
)
from apps.siteconfig.tenant_config import (
    INTERNAL_TENANT_SETTINGS_KEYS,
    apply_tenant_settings_overrides,
    compile_effective_tenant_config,
    is_tenant_setting_editable,
    persist_compiled_tenant_config,
)
from apps.schools.models import School


class TenantConfigCompilerTests(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="USA",
            defaults={
                "name": "United States",
                "default_language": "en",
                "timezone": "America/New_York",
                "date_format": "MM/DD/YYYY",
                "grading_scale": "0-100",
                "default_currency": "USD",
                "academic_year_start_month": 9,
                "term_count_per_year": 2,
            },
        )
        self.plan = Plan.objects.create(
            name="Pro",
            slug="pro-plan",
            included_features=["library"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Compiler School",
            slug="compiler-school",
            subdomain="compiler-school",
            is_active=True,
            default_region=self.region,
            settings={"default_language": "fr", "custom_setting": "tenant-value"},
            addons=["transport"],
            plan=self.plan,
        )
        self.profile = EducationSystemProfile.objects.create(
            code="usa-en-pack",
            name="USA EN Pack",
            region=self.region,
            sub_system=EducationSystemProfile.SubSystem.EN,
            is_default=True,
            is_active=True,
            approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
            approved_at=timezone.now(),
            default_language="en",
            default_currency="USD",
            default_timezone="America/New_York",
            grading_scale="0-100",
            config={"date_format": "YYYY-MM-DD"},
        )
        SystemFeature.objects.create(system=self.profile, feature_key="attendance")
        TenantSystem.objects.create(school=self.school, system=self.profile)

    def test_compiler_applies_precedence_and_lock_metadata(self):
        compiled = compile_effective_tenant_config(self.school)
        effective = compiled["effective"]
        metadata = compiled["metadata"]

        # tenant override beats profile/pack
        self.assertEqual(effective["default_language"], "fr")
        self.assertEqual(effective["custom_setting"], "tenant-value")

        # pack lock metadata present for compliance keys
        self.assertIn("privacy_framework", metadata)
        self.assertTrue(metadata["privacy_framework"]["compliance_locked"])
        self.assertFalse(metadata["privacy_framework"]["tenant_editable"])

        # plan + addons + tenant systems merge into feature_modules
        modules = set(effective.get("feature_modules") or [])
        self.assertIn("library", modules)
        self.assertIn("transport", modules)
        self.assertIn("attendance", modules)

    def test_editable_helper_respects_locks(self):
        compiled = compile_effective_tenant_config(self.school)
        self.assertFalse(is_tenant_setting_editable(compiled, "privacy_framework"))
        self.assertTrue(is_tenant_setting_editable(compiled, "default_language"))

    def test_low_connectivity_pack_defaults_offline_mode(self):
        cmr, _ = RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={
                "name": "Cameroon",
                "default_language": "en",
                "timezone": "Africa/Douala",
                "date_format": "DD/MM/YYYY",
                "grading_scale": "0-20",
                "default_currency": "XAF",
                "academic_year_start_month": 9,
                "term_count_per_year": 3,
            },
        )
        school = School.objects.create(
            name="LCA School",
            slug="lca-school",
            subdomain="lca-school",
            is_active=True,
            default_region=cmr,
        )
        compiled = compile_effective_tenant_config(school)
        self.assertTrue(compiled["effective"]["offline_mode_default"])

    def test_compiler_ignores_internal_snapshot_keys(self):
        self.school.settings = {
            **(self.school.settings or {}),
            "tenant_compiled_config": {"default_language": "de"},
            "tenant_config_metadata": {"default_language": {"tenant_editable": False}},
            "tenant_config_layers": ["tenant_override"],
            "tenant_policy_pack": {"code": "EU"},
            "tenant_config_compiled_at": "2026-01-01T00:00:00+00:00",
        }
        self.school.save(update_fields=["settings", "updated_at"])

        compiled = compile_effective_tenant_config(self.school)
        effective = compiled["effective"]

        self.assertEqual(effective["default_language"], "fr")
        for key in INTERNAL_TENANT_SETTINGS_KEYS:
            self.assertNotIn(key, effective)

    def test_persist_compiled_tenant_config_writes_snapshot(self):
        compiled = persist_compiled_tenant_config(self.school, persist=True)
        self.school.refresh_from_db()
        settings = self.school.settings or {}

        self.assertIn("tenant_compiled_config", settings)
        self.assertIn("tenant_config_metadata", settings)
        self.assertIn("tenant_config_layers", settings)
        self.assertIn("tenant_policy_pack", settings)
        self.assertIn("tenant_config_compiled_at", settings)
        self.assertEqual(
            settings.get("tenant_compiled_config"), compiled.get("effective")
        )

    def test_apply_tenant_settings_overrides_blocks_locked_keys(self):
        result = apply_tenant_settings_overrides(
            self.school,
            {
                "privacy_framework": "custom_framework",
                "default_language": "es",
            },
            actor_is_superadmin=False,
            force_override=False,
            persist=True,
        )
        self.school.refresh_from_db()
        settings = self.school.settings or {}

        self.assertEqual(result["applied"].get("default_language"), "es")
        self.assertIn("privacy_framework", result["blocked"])
        self.assertIn("privacy_framework", result["requires_approval"])
        self.assertEqual(settings.get("default_language"), "es")
        self.assertNotEqual(settings.get("privacy_framework"), "custom_framework")

    def test_apply_tenant_settings_overrides_allows_superadmin_force(self):
        result = apply_tenant_settings_overrides(
            self.school,
            {"privacy_framework": "custom_framework"},
            actor_is_superadmin=True,
            force_override=True,
            persist=True,
        )
        self.school.refresh_from_db()
        settings = self.school.settings or {}

        self.assertEqual(result["blocked"], {})
        self.assertEqual(settings.get("privacy_framework"), "custom_framework")
