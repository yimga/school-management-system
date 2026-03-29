"""Operator default report-platform bundle singleton + manifest surfacing."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.platform_runtime.models import PlatformReportPlatformSkuDefault
from apps.siteconfig.billing_sku_registry import manifest_plan_entitlements_block


class PlatformReportPlatformSkuDefaultTests(TestCase):
    def test_clean_rejects_unknown_bundle_slug(self):
        obj = PlatformReportPlatformSkuDefault(
            pk=1, default_bundle_slug="not-a-real-bundle"
        )
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_manifest_includes_operator_default_when_row_set(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug="reports-advanced"
        )
        pe = manifest_plan_entitlements_block()
        self.assertEqual(
            pe.get("operator_default_report_platform_bundle"), "reports-advanced"
        )

    def test_manifest_omits_operator_default_for_invalid_stored_slug(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug="bogus-slug"
        )
        # Row bypasses ORM validation — manifest must not emit unknown slugs.
        pe = manifest_plan_entitlements_block()
        self.assertNotIn("operator_default_report_platform_bundle", pe)
