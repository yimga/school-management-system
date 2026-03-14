"""
§12 gate: marketplace/packs deeply productized.

Verification for RUNMYCAMPUS §12 and BACKLOG §6.3. Catalog counts must meet
MARKETPLACE_SEED_TARGETS minimums so the marketplace is product-grade (not optional).
Run in pre_deploy_gate so the gate is mechanically enforced.
"""
from django.core.management import call_command
from django.test import TestCase

from apps.platform_runtime.catalog_counts import get_platform_catalog_counts

# MARKETPLACE_SEED_TARGETS.md §1 minimums (must match doc)
MIN_FIRST_PARTY_APPS = 25
MIN_BLUEPRINT_PACKS = 25
MIN_WORKFLOW_PACKS = 30
MIN_DASHBOARD_PACKS = 20
MIN_POLICY_BUNDLES = 15


def setUpModule():
    """Seed catalog so test DB meets MARKETPLACE_SEED_TARGETS minimums (pre_deploy_gate)."""
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
        self.assertGreaterEqual(
            counts.get("first_party_apps", 0),
            MIN_FIRST_PARTY_APPS,
            f"first_party_apps must be >= {MIN_FIRST_PARTY_APPS} (MARKETPLACE_SEED_TARGETS)",
        )
        self.assertGreaterEqual(
            counts.get("blueprint_packs", 0),
            MIN_BLUEPRINT_PACKS,
            f"blueprint_packs must be >= {MIN_BLUEPRINT_PACKS} (MARKETPLACE_SEED_TARGETS)",
        )
        self.assertGreaterEqual(
            counts.get("workflow_packs", 0),
            MIN_WORKFLOW_PACKS,
            f"workflow_packs must be >= {MIN_WORKFLOW_PACKS} (MARKETPLACE_SEED_TARGETS)",
        )
        self.assertGreaterEqual(
            counts.get("dashboard_packs", 0),
            MIN_DASHBOARD_PACKS,
            f"dashboard_packs must be >= {MIN_DASHBOARD_PACKS} (MARKETPLACE_SEED_TARGETS)",
        )
        self.assertGreaterEqual(
            counts.get("policy_bundles", 0),
            MIN_POLICY_BUNDLES,
            f"policy_bundles must be >= {MIN_POLICY_BUNDLES} (MARKETPLACE_SEED_TARGETS)",
        )
