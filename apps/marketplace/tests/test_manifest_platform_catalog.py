"""Platform manifest schema, pack catalog registry, and tenant catalog signals."""

from types import SimpleNamespace

from django.test import TestCase

from apps.marketplace.manifest_schema import (
    ROLLOUT_BETA,
    classify_scope_access,
    compatibility_signals_for_listing,
    entitlement_hints_for_school,
    listing_pipeline_phase,
    normalize_platform_manifest,
    platform_app_version,
    resolve_tenant_catalog_signals,
    validate_manifest_keys,
)
from apps.marketplace.models import (
    AppInstallation,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.siteconfig.models import Plan
from apps.marketplace.pack_registry import (
    load_platform_pack_catalog,
    validate_platform_pack_catalog,
)
from apps.marketplace.services import install_app
from apps.marketplace.views import _tenant_plan_display_context
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import Plan


class ManifestSchemaTests(TestCase):
    def test_normalize_sets_app_key_and_version_overlay(self):
        raw = {"scopes": ["x"], "required_features": ["reports"], "category": "ops"}
        out = normalize_platform_manifest(
            raw,
            app_slug="demo-app",
            app_name="Demo",
            version="2.1.0",
            publisher_slug="acme",
        )
        self.assertEqual(out["app_key"], "demo-app")
        self.assertEqual(out["version"], "2.1.0")
        self.assertEqual(out["required_features"], ["reports"])
        self.assertIn("scopes", out)
        self.assertEqual(out.get("required_commercial_tier"), "")

    def test_validate_manifest_warns_on_bad_required_features_type(self):
        w = validate_manifest_keys({"required_features": "oops"})
        self.assertTrue(any("required_features" in x for x in w))

    def test_classify_scope_access_tiers(self):
        self.assertEqual(classify_scope_access("resource:admin"), "admin")
        self.assertEqual(classify_scope_access("students.write", sensitive=False), "write")
        self.assertEqual(classify_scope_access("students.read"), "read")
        self.assertEqual(classify_scope_access("x", sensitive=True), "admin")

    def test_normalize_includes_tenant_editable_config_keys(self):
        out = normalize_platform_manifest(
            {"tenant_editable_config_keys": ["notify_email", " webhook_url "]},
            app_slug="a",
            app_name="A",
            version="1",
        )
        self.assertEqual(out["tenant_editable_config_keys"], ["notify_email", "webhook_url"])

    def test_normalize_merges_permissions_and_scopes(self):
        out = normalize_platform_manifest(
            {
                "permissions": ["a.read", "b.write"],
                "scopes": ["b.write", "c.admin"],
            },
            app_slug="x",
            app_name="X",
            version="1.0.0",
        )
        self.assertEqual(out["permissions"], ["a.read", "b.write", "c.admin"])
        self.assertEqual(out["scopes"], ["a.read", "b.write", "c.admin"])
        self.assertEqual(out.get("pricing_kind"), "included")

    def test_listing_pipeline_phase_maps_status(self):
        from apps.marketplace.models import MarketplaceListing

        self.assertEqual(
            listing_pipeline_phase(
                SimpleNamespace(status=MarketplaceListing.Status.DRAFT)
            ),
            "draft",
        )

    def test_mission_prompt_canonical_manifest_keys_populated(self):
        """
        Agent 2 / Marketplace Platform: schema must expose these keys end-to-end
        (normalize_platform_manifest overlay).
        """
        m = normalize_platform_manifest(
            {
                "category": "attendance",
                "required_features": ["library"],
                "required_plan": "pro",
                "dependencies": ["pack:a"],
            },
            app_slug="mission-app",
            app_name="Mission",
            version="3.0.0",
            publisher_slug="acme",
        )
        for key in (
            "app_key",
            "name",
            "category",
            "version",
            "publisher",
            "required_plan",
            "required_features",
            "permissions",
            "scopes",
            "dependencies",
            "configurable",
            "installable",
            "rollout_status",
        ):
            self.assertIn(key, m, msg=key)
        self.assertEqual(m["app_key"], "mission-app")
        self.assertEqual(m["dependencies"], ["pack:a"])


class TenantPlanContextTests(TestCase):
    def test_tenant_plan_display_maps_enterprise_slug(self):
        plan = Plan.objects.create(name="Enterprise", slug="enterprise")
        school = School.objects.create(
            name="Plan Ctx",
            slug="plan-ctx",
            subdomain="plan-ctx",
            is_active=True,
            plan=plan,
        )
        try:
            ctx = _tenant_plan_display_context(school)
            self.assertEqual(ctx["tier_key"], "enterprise")
            self.assertEqual(ctx["tier_label"], "Enterprise")
        finally:
            school.delete()
            plan.delete()


class PackCatalogRegistryTests(TestCase):
    def test_load_platform_pack_catalog_has_workflow_and_dashboard_entries(self):
        data = load_platform_pack_catalog()
        self.assertGreaterEqual(len(data.get("workflow_packs") or []), 5)
        self.assertGreaterEqual(len(data.get("dashboard_packs") or []), 4)
        self.assertGreaterEqual(len(data.get("theme_packs") or []), 1)
        msgs = validate_platform_pack_catalog(data)
        self.assertEqual(msgs, [], msg=msgs)


class TenantCatalogSignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.publisher = PublisherOrganization.objects.create(
            slug="sig-pub",
            name="Signal Pub",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )
        cls.app = MarketplaceApp.objects.create(
            slug="signal-app",
            name="Signal App",
            version="2.0.0",
            manifest={
                "required_features": ["nonexistent_feature_xyz"],
                "pricing_type": "paid",
                "price_display": "$12/mo",
                "rollout_status": ROLLOUT_BETA,
            },
            publisher=cls.publisher,
            is_intentionally_free=True,
        )
        cls.listing = MarketplaceListing.objects.create(
            app=cls.app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            category="analytics",
            short_description="Test listing",
            metadata={"rollout_status": ROLLOUT_BETA},
        )

    def test_entitlement_hints_when_feature_missing(self):
        school = School.objects.create(
            name="Sig School",
            slug="sig-school",
            subdomain="sig-school",
            is_active=True,
            features={},
        )
        try:
            hints = entitlement_hints_for_school(
                school,
                normalize_platform_manifest(
                    self.app.manifest,
                    app_slug=self.app.slug,
                    app_name=self.app.name,
                    version=self.app.version,
                ),
            )
            self.assertTrue(hints["blocked"])
            self.assertIn("nonexistent_feature_xyz", hints["missing_features"])
        finally:
            school.delete()

    def test_entitlement_hints_paid_blocked_on_free_tier_trial_without_stripe_customer(
        self,
    ):
        plan = Plan.objects.create(
            name="Community",
            slug="community",
            included_features=[],
            is_active=True,
        )
        school = School.objects.create(
            name="Trial Paid Gate",
            slug="trial-paid-gate",
            subdomain="trial-paid-gate",
            is_active=True,
            plan=plan,
            billing_type=School.BillingType.FREE_TRIAL,
            features={"library": True},
        )
        try:
            hints = entitlement_hints_for_school(
                school,
                normalize_platform_manifest(
                    {
                        "pricing_type": "paid",
                        "price_display": "$9",
                        "required_features": [],
                    },
                    app_slug="paid-gate",
                    app_name="Paid Gate",
                    version="1.0.0",
                ),
            )
            self.assertTrue(hints.get("monetization_blocked"))
            self.assertTrue(hints["blocked"])
        finally:
            school.delete()
            plan.delete()

    def test_entitlement_hints_commercial_tier_blocked(self):
        plan = Plan.objects.create(
            name="Starter",
            slug="starter",
            included_features=[],
            is_active=True,
        )
        school = School.objects.create(
            name="Tier School",
            slug="tier-school",
            subdomain="tier-school",
            is_active=True,
            plan=plan,
            features={"library": True},
        )
        try:
            hints = entitlement_hints_for_school(
                school,
                normalize_platform_manifest(
                    {
                        "required_commercial_tier": "enterprise",
                        "required_features": [],
                    },
                    app_slug="ent-app",
                    app_name="Ent",
                    version="1.0.0",
                ),
            )
            self.assertTrue(hints["blocked"])
            self.assertFalse(hints["commercial_tier_ok"])
            self.assertEqual(hints["required_commercial_tier"], "enterprise")
        finally:
            school.delete()
            plan.delete()

    def test_activate_sandbox_raises_when_entitlements_blocked(self):
        plan = Plan.objects.create(
            name="Starter",
            slug="basic",
            included_features=[],
            is_active=True,
        )
        school = School.objects.create(
            name="Act School",
            slug="act-school",
            subdomain="act-school",
            is_active=True,
            plan=plan,
            features={},
        )
        app = MarketplaceApp.objects.create(
            slug="tier-gate-app",
            name="Tier Gate",
            version="1.0.0",
            manifest={"required_commercial_tier": "enterprise"},
            publisher=self.publisher,
            is_intentionally_free=True,
        )
        try:
            inst = install_app(school, app, skip_compatibility=True)
            from apps.marketplace.services import activate_sandbox_installation

            with self.assertRaises(ValueError):
                activate_sandbox_installation(inst)
        finally:
            AppInstallation.objects.filter(school=school).delete()
            app.delete()
            school.delete()
            plan.delete()

    def test_resolve_signals_update_available_after_install_version_stamp(self):
        school = School.objects.create(
            name="Up School",
            slug="up-school",
            subdomain="up-school",
            is_active=True,
            features={},
        )
        try:
            inst = install_app(school, self.app, skip_compatibility=True)
            self.assertEqual((inst.config or {}).get("installed_catalog_version"), "2.0.0")
            self.app.version = "3.0.0"
            self.app.save(update_fields=["version"])
            sig = resolve_tenant_catalog_signals(
                listing=self.listing,
                school=school,
                installation=inst,
                listing_installable=self.listing.installable,
            )
            self.assertEqual(sig["lifecycle"], "active")
            self.assertTrue(sig["show_update"])
            sm = sig["state_machine"]
            self.assertTrue(sm["installed"])
            self.assertTrue(sm["active"])
            self.assertFalse(sm["disabled"])
            self.assertTrue(sm["update_available"])
            self.assertEqual(sm["installed_catalog_version"], "2.0.0")
            self.assertEqual(sm["catalog_version"], "3.0.0")
            self.assertIn("compatibility_ok", sm)
            self.assertIn("available", sm)
            for mission_k in (
                "available",
                "installed",
                "active",
                "disabled",
                "update_available",
                "rollback_available",
                "previous_catalog_version",
                "compatibility_ok",
                "compatibility_messages",
                "safe_rollback_eligible",
            ):
                self.assertIn(mission_k, sm, msg=mission_k)
        finally:
            AppInstallation.objects.filter(school=school).delete()
            school.delete()
            self.app.version = "2.0.0"
            self.app.save(update_fields=["version"])


class InstallVersionStampTests(TestCase):
    """previous_catalog_version is recorded when re-install bumps catalog semver."""

    @classmethod
    def setUpTestData(cls):
        cls.publisher = PublisherOrganization.objects.create(
            slug="stamp-pub",
            name="Stamp Pub",
        )
        cls.app = MarketplaceApp.objects.create(
            slug="stamp-app",
            name="Stamp App",
            version="1.0.0",
            manifest={},
            publisher=cls.publisher,
            is_intentionally_free=True,
        )
        MarketplaceListing.objects.create(
            app=cls.app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
        )

    def test_reinstall_sets_previous_catalog_version(self):
        school = School.objects.create(
            name="Stamp School",
            slug="stamp-school",
            subdomain="stamp-school",
            is_active=True,
        )
        try:
            install_app(school, self.app, skip_compatibility=True)
            self.app.version = "2.0.0"
            self.app.save(update_fields=["version"])
            install_app(school, self.app, skip_compatibility=True)
            inst = AppInstallation.objects.get(school=school, app=self.app)
            cfg = inst.config or {}
            self.assertEqual(cfg.get("installed_catalog_version"), "2.0.0")
            self.assertEqual(cfg.get("previous_catalog_version"), "1.0.0")
        finally:
            AppInstallation.objects.filter(school=school).delete()
            school.delete()
            self.app.version = "1.0.0"
            self.app.save(update_fields=["version"])


class PlatformCompatSignalsTests(TestCase):
    def test_platform_version_readable(self):
        v = platform_app_version()
        self.assertTrue(len(v) >= 3)

    def test_compatibility_signals_calls_services_warn_only(self):
        publisher = PublisherOrganization.objects.create(
            slug="compat-pub", name="Compat Pub"
        )
        app = MarketplaceApp.objects.create(
            slug="compat-app",
            name="Compat",
            version="1.0.0",
            manifest={"min_platform_version": "0.0.1"},
            publisher=publisher,
            is_intentionally_free=True,
        )
        listing = MarketplaceListing.objects.create(
            app=app,
            publisher=publisher,
            status=MarketplaceListing.Status.APPROVED,
        )
        school = School.objects.create(
            name="C School",
            slug="c-school",
            subdomain="c-school",
            is_active=True,
        )
        try:
            mf = normalize_platform_manifest(
                app.manifest,
                app_slug=app.slug,
                app_name=app.name,
                version=app.version,
            )
            sig = compatibility_signals_for_listing(school, listing, mf)
            self.assertIn("ok", sig)
            self.assertIsInstance(sig.get("messages"), list)
        finally:
            school.delete()
