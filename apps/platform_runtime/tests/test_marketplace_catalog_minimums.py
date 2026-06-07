"""
§12 gate: marketplace/packs deeply productized.

Verification for RUNMYCAMPUS §12 and BACKLOG §6.3. Catalog counts must meet
MARKETPLACE_SEED_TARGETS minimums so the marketplace is product-grade (not optional).
Run in pre_deploy_gate so the gate is mechanically enforced.
"""

from django.core.management import call_command
from django.test import TestCase

from apps.platform_runtime.catalog_counts import (
    MARKETPLACE_MINIMUMS,
    get_platform_catalog_counts,
    satisfies_marketplace_minimums,
)


def setUpModule():
    """Seed catalog so test DB meets MARKETPLACE_SEED_TARGETS minimums (pre_deploy_gate)."""
    call_command("seed_marketplace_apps", verbosity=0)
    call_command("seed_marketplace_catalog_packages", verbosity=0)
    call_command("seed_first_party_apps", verbosity=0)
    call_command("seed_blueprint_policy_packs", verbosity=0)
    call_command("seed_workflow_dashboard_packs", verbosity=0)


class MarketplaceCatalogMinimumsTests(TestCase):
    """§12 marketplace/packs deeply productized: catalog meets minimums."""

    def test_platform_catalog_meets_marketplace_seed_minimums(self):
        """
        get_platform_catalog_counts() must meet MARKETPLACE_SEED_TARGETS minimums.
        Required for §12 gate 'marketplace/packs deeply productized' (not optional).
        """
        counts = get_platform_catalog_counts()
        ok, errors = satisfies_marketplace_minimums(counts)
        self.assertTrue(ok, "Catalog must meet minimums: " + "; ".join(errors))
        for key, minimum in MARKETPLACE_MINIMUMS.items():
            self.assertGreaterEqual(
                counts.get(key, 0),
                minimum,
                f"{key} must be >= {minimum} (MARKETPLACE_SEED_TARGETS §1)",
            )

    def test_satisfies_marketplace_minimums_helper(self):
        """satisfies_marketplace_minimums() returns True when counts meet minimums."""
        counts = get_platform_catalog_counts()
        ok, errors = satisfies_marketplace_minimums(counts)
        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])

    def test_seed_commands_are_idempotent(self):
        """Running seed commands a second time must not drop counts below minimums (§7)."""
        call_command("seed_first_party_apps", verbosity=0)
        call_command("seed_blueprint_policy_packs", verbosity=0)
        call_command("seed_workflow_dashboard_packs", verbosity=0)
        counts = get_platform_catalog_counts()
        ok, errors = satisfies_marketplace_minimums(counts)
        self.assertTrue(
            ok, "Idempotent seed run must still meet minimums: " + "; ".join(errors)
        )
