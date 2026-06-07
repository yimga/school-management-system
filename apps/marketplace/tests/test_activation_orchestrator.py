"""Wave 2/3 — activation orchestrator enables features on sandbox → active."""

from django.test import TestCase

from apps.marketplace.activation_orchestrator import (
    apply_capability_bindings_on_activate,
    revert_capability_bindings_on_uninstall,
)
from apps.marketplace.models import (
    AppInstallation,
    AppScope,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.schools.models import School


class ActivationOrchestratorTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Orchestrator School",
            slug="orchestrator-school",
            subdomain="orchestrator-school",
            is_active=True,
            features={},
        )
        self.publisher = PublisherOrganization.objects.create(
            slug="test-publisher-orch",
            name="Test Publisher",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )
        manifest = {
            "scopes": ["transport"],
            "widgets": [],
            "wedge_ids": [14, 33],
            "capability_bindings": [
                {
                    "kind": "feature",
                    "target": "transport",
                    "mode": "enable_on_activate",
                },
                {
                    "kind": "package_id",
                    "target": "transport-bus-tracker-orch-test",
                    "mode": "apply_on_activate",
                },
            ],
        }
        self.app = MarketplaceApp.objects.create(
            slug="transport-bus-tracker-orch-test",
            app_key="transport-bus-tracker-orch-test",
            name="Transport Test",
            publisher=self.publisher,
            version="1.0",
            manifest=manifest,
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            pricing_model=MarketplaceApp.PricingModel.FREE,
            is_intentionally_free=True,
            is_active=True,
        )
        MarketplaceListing.objects.create(
            app=self.app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
        )
        AppScope.objects.create(
            app=self.app,
            scope_code="transport",
            description="transport scope",
        )
        self.installation = AppInstallation.objects.create(
            school=self.school,
            app=self.app,
            status=AppInstallation.Status.ACTIVE,
            install_phase=AppInstallation.InstallPhase.SANDBOX,
        )

    def test_activate_enables_transport_feature(self):
        result = apply_capability_bindings_on_activate(
            self.installation,
            manifest=self.app.manifest,
        )
        self.school.refresh_from_db()
        self.assertIn("transport", result.get("features_enabled") or [])
        self.assertTrue((self.school.features or {}).get("transport"))

    def test_uninstall_clears_feature_when_only_install(self):
        apply_capability_bindings_on_activate(
            self.installation,
            manifest=self.app.manifest,
        )
        revert_capability_bindings_on_uninstall(self.installation)
        self.school.refresh_from_db()
        self.assertFalse((self.school.features or {}).get("transport"))

    def test_activate_applies_package_when_payload_exists(self):
        from apps.marketplace.marketplace_package_payloads import (
            build_marketplace_package_payload,
        )
        from apps.packages.models import InstalledPackage, PackageVersion

        pid = "transport-bus-tracker-orch-test"
        payload = build_marketplace_package_payload(
            slug=pid,
            name="Transport Test",
            version="1.0",
            manifest=self.app.manifest,
        )
        PackageVersion.objects.update_or_create(
            package_id=pid,
            version="1.0",
            defaults={"payload_sections": payload},
        )
        result = apply_capability_bindings_on_activate(
            self.installation,
            manifest=self.app.manifest,
        )
        self.assertIn(pid, result.get("packages_applied") or [])
        self.assertTrue(
            InstalledPackage.objects.filter(
                school=self.school,
                package_id=pid,
                is_active=True,
            ).exists()
        )
