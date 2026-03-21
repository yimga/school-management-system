from django.test import SimpleTestCase

from apps.siteconfig import brand_registry, branding, metadata_catalog
from apps.siteconfig import admin as siteconfig_admin
from apps.siteconfig import forms as siteconfig_forms
from apps.siteconfig import views as siteconfig_views
from apps.siteconfig.models import (
    BrandProfile as LegacyBrandProfile,
    FeatureToggleDefinition,
    Integration as LegacyIntegration,
    RegionConfig as LegacyRegionConfig,
    ThemePack as LegacyThemePack,
)
from apps.siteconfig.models_dashboard import DashboardPack as LegacyDashboardPack
from apps.siteconfig.models_workflow import WorkflowPack as LegacyWorkflowPack
from apps.brand_experience.models import ThemePack
from apps.global_registries.models import RegionConfig
from apps.integrations_marketplace.models import Integration, MarketplaceListing
from apps.plans_entitlements.models import CountryMultiplier, Plan
from apps.runtime_blueprints.models import BlueprintPack, DashboardPack, WorkflowPack
from config.admin import platform_admin_site, tenant_admin_site


class BoundedContextOwnershipTests(SimpleTestCase):
    def test_brand_experience_uses_proxy_owner_models(self):
        self.assertTrue(ThemePack._meta.proxy)
        self.assertEqual(ThemePack._meta.app_label, "brand_experience")

    def test_runtime_blueprints_uses_proxy_owner_models(self):
        self.assertTrue(BlueprintPack._meta.proxy)
        self.assertEqual(BlueprintPack._meta.app_label, "runtime_blueprints")
        self.assertTrue(DashboardPack._meta.proxy)
        self.assertTrue(WorkflowPack._meta.proxy)

    def test_plans_entitlements_uses_proxy_owner_models(self):
        self.assertTrue(Plan._meta.proxy)
        self.assertEqual(Plan._meta.app_label, "plans_entitlements")

    def test_global_registries_uses_proxy_owner_models(self):
        self.assertTrue(RegionConfig._meta.proxy)
        self.assertEqual(RegionConfig._meta.app_label, "global_registries")

    def test_integrations_marketplace_uses_proxy_owner_models(self):
        self.assertTrue(Integration._meta.proxy)
        self.assertEqual(Integration._meta.app_label, "integrations_marketplace")
        self.assertTrue(MarketplaceListing._meta.proxy)

    def test_successor_owner_models_drive_catalog_and_branding_surfaces(self):
        self.assertEqual(branding.BrandProfile._meta.app_label, "brand_experience")
        self.assertEqual(branding.BrandSettings._meta.app_label, "brand_experience")
        self.assertEqual(
            brand_registry.GlobalBrandRegistry._meta.app_label, "brand_experience"
        )
        self.assertEqual(metadata_catalog.ThemePack._meta.app_label, "brand_experience")
        self.assertEqual(metadata_catalog.CountryRegistry._meta.app_label, "registries")
        self.assertEqual(
            metadata_catalog.Integration._meta.app_label, "integrations_marketplace"
        )

    def test_siteconfig_operator_surfaces_use_successor_theme_owner_model(self):
        # ThemePack and ReportCardStyle used by siteconfig forms/admin/views are successor proxies.
        self.assertEqual(siteconfig_forms.ThemePack._meta.app_label, "brand_experience")
        self.assertEqual(siteconfig_admin.ThemePack._meta.app_label, "brand_experience")
        # BrandProfile/BrandSettings are registered in brand_experience.admin only (see branding.BrandProfile).
        self.assertEqual(
            siteconfig_forms.ReportCardStyle._meta.app_label, "runtime_blueprints"
        )
        self.assertEqual(
            siteconfig_views.ReportCardStyle._meta.app_label, "runtime_blueprints"
        )

    def test_successor_owner_models_are_registered_in_platform_admin(self):
        for model in (
            ThemePack,
            BlueprintPack,
            DashboardPack,
            WorkflowPack,
            Integration,
            MarketplaceListing,
        ):
            self.assertIn(model, platform_admin_site._registry)

    def test_plan_and_region_catalog_not_on_platform_admin_super_crud_instead(self):
        """Plan / RegionConfig CRUD lives on super control plane, not platform /admin/."""
        self.assertNotIn(Plan, platform_admin_site._registry)
        self.assertNotIn(RegionConfig, platform_admin_site._registry)
        self.assertNotIn(CountryMultiplier, platform_admin_site._registry)
        self.assertNotIn(CountryMultiplier, tenant_admin_site._registry)
        self.assertNotIn(FeatureToggleDefinition, platform_admin_site._registry)
        self.assertIn(FeatureToggleDefinition, tenant_admin_site._registry)

    def test_legacy_siteconfig_models_are_not_the_visible_admin_owner(self):
        for model in (
            LegacyThemePack,
            LegacyBrandProfile,
            LegacyIntegration,
            LegacyRegionConfig,
            LegacyDashboardPack,
            LegacyWorkflowPack,
        ):
            self.assertNotIn(model, platform_admin_site._registry)
            self.assertNotIn(model, tenant_admin_site._registry)
