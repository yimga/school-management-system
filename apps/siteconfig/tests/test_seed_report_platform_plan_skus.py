"""Management command: Plan rows for report-platform SKU bundles."""

from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.billing_sku_registry import (
    REPORT_PLATFORM_SKU_ADVANCED,
    REPORT_PLATFORM_SKU_STANDARD,
    ordered_features_for_report_platform_bundle,
)
from apps.siteconfig.models_platform_catalog import Plan


class SeedReportPlatformPlanSkusCommandTests(TestCase):
    def test_upserts_standard_and_advanced_plans(self):
        call_command("seed_report_platform_plan_skus", verbosity=0)
        std = Plan.objects.get(slug="report-platform-standard")
        adv = Plan.objects.get(slug="report-platform-advanced")
        self.assertEqual(
            std.included_features,
            ordered_features_for_report_platform_bundle(REPORT_PLATFORM_SKU_STANDARD),
        )
        self.assertEqual(
            adv.included_features,
            ordered_features_for_report_platform_bundle(REPORT_PLATFORM_SKU_ADVANCED),
        )
        self.assertTrue(std.is_active)
        self.assertTrue(adv.is_active)

    def test_idempotent_second_run(self):
        call_command("seed_report_platform_plan_skus", verbosity=0)
        pk_std = Plan.objects.get(slug="report-platform-standard").pk
        call_command("seed_report_platform_plan_skus", verbosity=0)
        self.assertEqual(Plan.objects.get(slug="report-platform-standard").pk, pk_std)
