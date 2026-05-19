"""Tenant overview viz service + Python seeder."""

from django.test import SimpleTestCase, TestCase

from apps.analytics.services.analytics_seeder_py import (
    seed_tenant_analytics_bundle,
    validate_bundle_integrity,
)
from apps.analytics.services.tenant_overview_viz import build_tenant_overview_bundle
from apps.schools.models import School


class AnalyticsSeederPyTests(SimpleTestCase):
    def test_seed_integrity(self):
        bundle = seed_tenant_analytics_bundle("audit-tenant")
        ok, errors = validate_bundle_integrity(bundle)
        self.assertTrue(ok, errors)
        self.assertGreater(bundle["totals"]["revenue"], 0)


class BuildTenantOverviewBundleTests(TestCase):
    def test_demo_slug_uses_seed(self):
        bundle = build_tenant_overview_bundle(tenant_id="marketing-demo", school=None)
        self.assertEqual(bundle["meta"]["source"], "seed-demo")
        self.assertEqual(bundle["tenantId"], "marketing-demo")

    def test_live_school_empty_series(self):
        school = School.objects.create(
            name="Empty Viz",
            slug="empty-viz-school",
            subdomain="empty-viz-school",
            is_active=True,
        )
        bundle = build_tenant_overview_bundle(
            tenant_id=school.slug,
            school=school,
        )
        self.assertEqual(bundle["meta"]["source"], "live")
        self.assertTrue(bundle["meta"]["empty"])
