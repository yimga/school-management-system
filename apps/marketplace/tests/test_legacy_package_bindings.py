"""Legacy package_id wiring on marketplace catalog listings."""

from django.core.management import call_command
from django.test import TestCase

from apps.marketplace.capability_contract import (
    enrich_manifest_capability_bindings,
    extract_capability_bindings,
)
from apps.marketplace.legacy_package_bindings import (
    CATALOG_SLUG_TO_LEGACY_PACKAGE_ID,
    LEGACY_PACKAGE_IDS,
    resolve_legacy_package_id,
)
from apps.marketplace.models import MarketplaceApp
from apps.marketplace.services import activate_sandbox_installation, install_app
from apps.packages.models import InstalledPackage
from apps.schools.models import School


class LegacyPackageBindingTests(TestCase):
    def test_all_legacy_ids_have_catalog_slug(self):
        mapped = set(CATALOG_SLUG_TO_LEGACY_PACKAGE_ID.values())
        self.assertEqual(mapped, set(LEGACY_PACKAGE_IDS))

    def test_admissions_lead_tracker_uses_admissions_core(self):
        manifest = enrich_manifest_capability_bindings("admissions-lead-tracker", {})
        self.assertEqual(manifest.get("package_id"), "admissions-core")
        bindings = extract_capability_bindings(manifest)
        pkg = [b["target"] for b in bindings if b["kind"] == "package_id"]
        self.assertIn("admissions-core", pkg)

    def test_billing_fees_pack_uses_finance_invoicing(self):
        self.assertEqual(
            resolve_legacy_package_id("billing-fees-pack"),
            "finance-invoicing",
        )


class LegacyPackageActivateTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command("seed_marketplace_apps", verbosity=0)
        call_command("seed_first_party_apps", verbosity=0)

    def setUp(self):
        self.school = School.objects.create(
            name="Legacy Package School",
            slug="legacy-package-school",
            subdomain="legacy-package-school",
            is_active=True,
            features={},
        )

    def test_activate_applies_legacy_package_for_admissions(self):
        app = MarketplaceApp.objects.get(slug="admissions-lead-tracker")
        inst = install_app(
            self.school,
            app,
            install_phase="sandbox",
            skip_compatibility=True,
        )
        activate_sandbox_installation(inst)
        inst.refresh_from_db()
        applied = (inst.config or {}).get("capability_packages_applied") or []
        self.assertIn("admissions-core", applied)
        self.assertTrue(
            InstalledPackage.objects.filter(
                school=self.school,
                package_id="admissions-core",
                is_active=True,
            ).exists()
        )
