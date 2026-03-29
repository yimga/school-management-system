"""Management command: seed_br10_plan_skus."""

from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.billing_sku_registry import (
    BR10_TIER_CORE,
    ordered_features_for_br10_tier,
)
from apps.siteconfig.models_platform_catalog import Plan


class SeedBr10PlanSkusCommandTests(TestCase):
    def test_creates_core_plan_with_registry_features(self):
        call_command("seed_br10_plan_skus", "--tier", BR10_TIER_CORE)
        plan = Plan.objects.get(slug="br10-core")
        self.assertEqual(plan.included_features, ordered_features_for_br10_tier(BR10_TIER_CORE))
        self.assertTrue(plan.is_active)

    def test_idempotent_update(self):
        Plan.objects.create(
            slug="br10-core",
            name="Old",
            included_features=["legacy"],
        )
        call_command("seed_br10_plan_skus", "--tier", BR10_TIER_CORE)
        plan = Plan.objects.get(slug="br10-core")
        self.assertEqual(plan.included_features, ordered_features_for_br10_tier(BR10_TIER_CORE))
        self.assertEqual(plan.name, "BR-10 Core")

    def test_ordered_features_helper_matches_sorted_bundle(self):
        self.assertEqual(
            ordered_features_for_br10_tier(BR10_TIER_CORE),
            sorted(ordered_features_for_br10_tier(BR10_TIER_CORE)),
        )
