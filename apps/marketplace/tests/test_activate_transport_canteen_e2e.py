"""
End-to-end: install → sandbox → activate for Transport and Canteen catalog apps.

Uses seeded marketplace apps + catalog PackageVersion payloads (batch 1637+).
"""

from django.core.management import call_command
from django.test import TestCase

from apps.marketplace.models import AppInstallation, MarketplaceApp
from apps.marketplace.services import activate_sandbox_installation, install_app
from apps.packages.models import InstalledPackage
from apps.schools.models import School


class ActivateTransportCanteenE2ETests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command("seed_marketplace_apps", verbosity=0)
        call_command("seed_marketplace_catalog_packages", verbosity=0)

    def setUp(self):
        self.school = School.objects.create(
            name="Schoolops Activate School",
            slug="schoolops-activate-school",
            subdomain="schoolops-activate-school",
            is_active=True,
            features={},
            settings={},
        )

    def _activate_catalog_app(self, slug: str) -> AppInstallation:
        app = MarketplaceApp.objects.get(slug=slug, is_active=True)
        installation = install_app(
            self.school,
            app,
            install_phase="sandbox",
            skip_compatibility=True,
        )
        self.assertEqual(installation.install_phase, AppInstallation.InstallPhase.SANDBOX)
        activate_sandbox_installation(installation)
        installation.refresh_from_db()
        self.assertEqual(installation.install_phase, AppInstallation.InstallPhase.ACTIVE)
        return installation

    def test_transport_activate_enables_feature_and_applies_package(self):
        inst = self._activate_catalog_app("transport-bus-tracker")
        self.school.refresh_from_db()
        self.assertTrue((self.school.features or {}).get("transport"))
        activation = (inst.config or {}).get("capability_packages_applied")
        self.assertIn("transport-bus-tracker", activation or [])
        self.assertTrue(
            InstalledPackage.objects.filter(
                school=self.school,
                package_id="transport-bus-tracker",
                is_active=True,
            ).exists()
        )

    def test_canteen_activate_enables_feature_and_applies_package(self):
        inst = self._activate_catalog_app("cafeteria-meal-plans")
        self.school.refresh_from_db()
        self.assertTrue((self.school.features or {}).get("canteen"))
        activation = (inst.config or {}).get("capability_packages_applied")
        self.assertIn("cafeteria-meal-plans", activation or [])
        self.assertTrue(
            InstalledPackage.objects.filter(
                school=self.school,
                package_id="cafeteria-meal-plans",
                is_active=True,
            ).exists()
        )
