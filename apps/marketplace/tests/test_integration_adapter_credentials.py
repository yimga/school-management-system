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


class IntegrationCredentialEditorTests(TestCase):
    def test_apply_credential_field_values_marks_configured(self):
        from apps.marketplace.integration_adapter_credentials import (
            apply_credential_field_values,
            build_credential_placeholder,
        )

        settings = {}
        placeholder = build_credential_placeholder("payments:paystack", app_slug="payments-paystack")
        settings["marketplace_integration_credentials"] = {
            "payments:paystack": placeholder,
        }
        settings, changed = apply_credential_field_values(
            settings,
            adapter_key="payments:paystack",
            field_values={
                "secret_key": "sk_test_abc",
                "public_key": "pk_test_xyz",
            },
        )
        self.assertTrue(changed)
        entry = settings["marketplace_integration_credentials"]["payments:paystack"]
        self.assertEqual(entry["status"], "configured")

    def test_credential_editor_view_requires_school(self):
        from unittest.mock import patch

        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.finance.models import ComplianceProfile
        from apps.finance.views_marketplace_integration_credentials import (
            marketplace_integration_credentials,
        )

        school = School.objects.create(
            name="Cred UI School",
            slug="cred-ui-school",
            subdomain="cred-ui-school",
            is_active=True,
            settings={
                "marketplace_integration_credentials": {
                    "payments:paystack": {
                        "adapter_key": "payments:paystack",
                        "status": "pending_operator_setup",
                        "fields": {
                            "secret_key": {
                                "label": "Secret",
                                "required": True,
                                "value": "",
                            },
                            "public_key": {
                                "label": "Public",
                                "required": True,
                                "value": "",
                            },
                        },
                    }
                }
            },
        )
        profile = ComplianceProfile.objects.create(
            name="NG Corridor",
            country_code="NG",
            currency_code="NGN",
            is_active=True,
        )
        user = User.objects.create_user(
            username="cred_editor",
            password="Test1234!",
            is_staff=True,
        )
        factory = RequestFactory()
        request = factory.get("/finance/integration-credentials/")
        request.user = user
        request.school = school
        with patch(
            "apps.finance.views_marketplace_integration_credentials._active_profile",
            return_value=profile,
        ):
            response = marketplace_integration_credentials(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"payments:paystack", response.content)


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
