"""BR-10 SKU registry parity with manifest (no duplicate strategy docs)."""

import json

from django.test import RequestFactory, TestCase

from apps.api.api_v1_manifest import api_v1_manifest
from apps.platform_runtime.models import PlatformReportPlatformSkuDefault
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.billing_sku_registry import (
    ALL_BR10_CANONICAL_FEATURE_CODES,
    ALL_REPORT_PLATFORM_FEATURE_CODES,
    BR10_TIER_CORE,
    BR10_TIER_FEATURE_BUNDLES,
    REPORT_PLATFORM_SKU_ADVANCED,
    REPORT_PLATFORM_SKU_BUNDLES,
    REPORT_PLATFORM_SKU_STANDARD,
    get_effective_report_platform_bundle_slug_for_school,
    get_effective_report_platform_floor_codes_for_school,
    get_operator_default_report_platform_bundle_slug,
    get_operator_report_platform_bundle_feature_codes,
    manifest_plan_entitlements_block,
    manifest_report_platform_skus_block,
    normalize_plan_feature_codes,
    ordered_features_for_report_platform_bundle,
    suggested_features_for_br10_tier,
)


class BillingSkuRegistryTests(TestCase):
    def test_tiers_cover_union(self):
        union = frozenset().union(*BR10_TIER_FEATURE_BUNDLES.values())
        self.assertEqual(union, ALL_BR10_CANONICAL_FEATURE_CODES)

    def test_normalize_plan_feature_codes(self):
        self.assertEqual(
            normalize_plan_feature_codes(["Reports", "reports", " Finance "]),
            ["reports", "finance"],
        )

    def test_suggested_bundle_core_non_empty(self):
        self.assertTrue(suggested_features_for_br10_tier(BR10_TIER_CORE))

    def test_manifest_includes_plan_entitlements(self):
        req = RequestFactory().get("/api/v1/manifest.json", HTTP_HOST="testserver")
        resp = api_v1_manifest(req)
        data = json.loads(resp.content.decode("utf-8"))
        pe = data.get("plan_entitlements") or {}
        self.assertIn("tiers", pe)
        self.assertIn(BR10_TIER_CORE, pe["tiers"])
        block = manifest_plan_entitlements_block()
        self.assertIn("all_canonical_codes", block)
        self.assertIn("report_platform_skus", block)
        rps = block["report_platform_skus"]
        self.assertIn(REPORT_PLATFORM_SKU_STANDARD, rps["bundles"])
        self.assertIn(REPORT_PLATFORM_SKU_ADVANCED, rps["bundles"])
        adv = frozenset(rps["bundles"][REPORT_PLATFORM_SKU_ADVANCED])
        std = frozenset(rps["bundles"][REPORT_PLATFORM_SKU_STANDARD])
        self.assertTrue(std.issubset(adv))

    def test_report_platform_bundles_cover_union(self):
        union = frozenset().union(*REPORT_PLATFORM_SKU_BUNDLES.values())
        self.assertEqual(union, ALL_REPORT_PLATFORM_FEATURE_CODES)

    def test_manifest_report_platform_block_matches_registry(self):
        m = manifest_report_platform_skus_block()
        self.assertEqual(
            set(m["all_feature_codes"]),
            set(ALL_REPORT_PLATFORM_FEATURE_CODES),
        )

    def test_ordered_features_for_report_platform_bundle(self):
        self.assertEqual(
            ordered_features_for_report_platform_bundle(REPORT_PLATFORM_SKU_STANDARD),
            sorted(REPORT_PLATFORM_SKU_BUNDLES[REPORT_PLATFORM_SKU_STANDARD]),
        )
        self.assertEqual(
            ordered_features_for_report_platform_bundle(REPORT_PLATFORM_SKU_ADVANCED),
            sorted(REPORT_PLATFORM_SKU_BUNDLES[REPORT_PLATFORM_SKU_ADVANCED]),
        )
        self.assertEqual(ordered_features_for_report_platform_bundle("unknown"), [])

    def test_get_operator_report_platform_bundle_feature_codes_empty_by_default(self):
        PlatformReportPlatformSkuDefault.objects.all().delete()
        self.assertEqual(get_operator_report_platform_bundle_feature_codes(), frozenset())

    def test_get_operator_report_platform_bundle_feature_codes_respects_singleton(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug=REPORT_PLATFORM_SKU_STANDARD
        )
        self.assertEqual(
            get_operator_report_platform_bundle_feature_codes(),
            REPORT_PLATFORM_SKU_BUNDLES[REPORT_PLATFORM_SKU_STANDARD],
        )

    def test_get_effective_floor_prefers_school_slug_over_operator(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug=REPORT_PLATFORM_SKU_ADVANCED
        )
        plan = Plan.objects.create(
            name="Eff floor plan",
            slug="eff-floor-plan",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="Eff floor school",
            slug="eff-floor-school",
            subdomain="eff-floor-school",
            is_active=True,
            plan=plan,
            report_platform_bundle_slug=REPORT_PLATFORM_SKU_STANDARD,
        )
        self.assertEqual(
            get_effective_report_platform_floor_codes_for_school(school),
            REPORT_PLATFORM_SKU_BUNDLES[REPORT_PLATFORM_SKU_STANDARD],
        )

    def test_get_effective_floor_none_school_matches_operator_only(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug=REPORT_PLATFORM_SKU_STANDARD
        )
        self.assertEqual(
            get_effective_report_platform_floor_codes_for_school(None),
            REPORT_PLATFORM_SKU_BUNDLES[REPORT_PLATFORM_SKU_STANDARD],
        )

    def test_get_operator_default_slug_matches_singleton(self):
        PlatformReportPlatformSkuDefault.objects.all().delete()
        self.assertIsNone(get_operator_default_report_platform_bundle_slug())
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug=REPORT_PLATFORM_SKU_ADVANCED
        )
        self.assertEqual(
            get_operator_default_report_platform_bundle_slug(),
            REPORT_PLATFORM_SKU_ADVANCED,
        )

    def test_get_effective_bundle_slug_prefers_school_with_cached_operator(self):
        school = School.objects.create(
            name="Slug school",
            slug="slug-school",
            subdomain="slug-school",
            is_active=True,
            report_platform_bundle_slug=REPORT_PLATFORM_SKU_STANDARD,
        )
        self.assertEqual(
            get_effective_report_platform_bundle_slug_for_school(
                school, operator_default_slug=REPORT_PLATFORM_SKU_ADVANCED
            ),
            REPORT_PLATFORM_SKU_STANDARD,
        )

    def test_get_effective_bundle_slug_uses_passed_operator_when_school_empty(self):
        school = School.objects.create(
            name="No override",
            slug="no-override",
            subdomain="no-override",
            is_active=True,
            report_platform_bundle_slug="",
        )
        self.assertEqual(
            get_effective_report_platform_bundle_slug_for_school(
                school, operator_default_slug=REPORT_PLATFORM_SKU_ADVANCED
            ),
            REPORT_PLATFORM_SKU_ADVANCED,
        )
