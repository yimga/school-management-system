"""Integration adapter credential placeholders on activate."""

from django.core.management import call_command
from django.test import TestCase

from apps.marketplace.activation_orchestrator import apply_capability_bindings_on_activate
from apps.marketplace.capability_contract import enrich_manifest_capability_bindings
from apps.marketplace.catalog_package_coverage import (
    catalog_native_slugs,
    package_binding_mode,
)
from apps.marketplace.integration_adapter_credentials import adapter_schema_validation_errors
from apps.marketplace.models import (
    AppInstallation,
    AppScope,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.schools.models import School


class IntegrationAdapterCredentialTests(TestCase):
    def test_adapter_schema_covers_catalog_integrations(self):
        self.assertEqual(adapter_schema_validation_errors(), [])

    def test_activate_seeds_paystack_credential_placeholder(self):
        school = School.objects.create(
            name="Paystack Cred School",
            slug="paystack-cred-school",
            subdomain="paystack-cred-school",
            is_active=True,
            settings={},
        )
        publisher = PublisherOrganization.objects.create(
            slug="paystack-publisher",
            name="Paystack Publisher",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )
        manifest = enrich_manifest_capability_bindings("payments-paystack", {})
        app = MarketplaceApp.objects.create(
            slug="payments-paystack-test",
            app_key="payments-paystack-test",
            name="Paystack Test",
            publisher=publisher,
            version="1.0",
            manifest=manifest,
            is_active=True,
            pricing_model=MarketplaceApp.PricingModel.FREE,
            is_intentionally_free=True,
        )
        MarketplaceListing.objects.create(
            app=app,
            publisher=publisher,
            status=MarketplaceListing.Status.APPROVED,
        )
        AppScope.objects.create(app=app, scope_code="finance", description="finance")
        inst = AppInstallation.objects.create(
            school=school,
            app=app,
            status=AppInstallation.Status.ACTIVE,
            install_phase=AppInstallation.InstallPhase.SANDBOX,
        )
        apply_capability_bindings_on_activate(inst, manifest=manifest)
        school.refresh_from_db()
        creds = (school.settings or {}).get("marketplace_integration_credentials") or {}
        self.assertIn("payments:paystack", creds)
        entry = creds["payments:paystack"]
        self.assertEqual(entry.get("status"), "pending_operator_setup")
        self.assertIn("secret_key", entry.get("fields") or {})


class CatalogNativeCoverageTests(TestCase):
    def test_transport_and_canteen_are_catalog_native(self):
        self.assertEqual(package_binding_mode("transport-bus-tracker"), "catalog_native")
        self.assertEqual(package_binding_mode("cafeteria-meal-plans"), "catalog_native")

    def test_catalog_native_slugs_include_schoolops_apps(self):
        natives = set(catalog_native_slugs())
        self.assertIn("transport-bus-tracker", natives)
        self.assertIn("cafeteria-meal-plans", natives)

    def test_full_catalog_package_coverage_after_seed(self):
        call_command("seed_marketplace_apps", verbosity=0)
        call_command("seed_marketplace_catalog_packages", verbosity=0)
        call_command("seed_first_party_apps", verbosity=0)
        from apps.marketplace.catalog_package_coverage import (
            catalog_package_coverage_errors,
        )

        self.assertEqual(catalog_package_coverage_errors(), [])
