"""Platform rollups helper (manager district / trust surfaces)."""

from django.test import TestCase

from apps.platform_runtime.identity_graph_rollups import (
    compute_platform_identity_rollups,
    compute_tenant_identity_graph_summary,
)
from apps.schools.models import School


class IdentityGraphRollupsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Rollup High",
            slug="rollup-high",
            subdomain="rollup-high",
            is_active=True,
            billing_type=School.BillingType.REGULAR,
        )

    def test_platform_rollups_has_schema(self):
        r = compute_platform_identity_rollups()
        self.assertEqual(r.get("schema_version"), "1.0")
        self.assertNotIn("error", r)
        self.assertIsNotNone(r.get("active_schools"))

    def test_tenant_summary_scoped_to_school(self):
        r = compute_tenant_identity_graph_summary(self.school)
        self.assertEqual(r.get("schema_version"), "1.0")
        self.assertEqual(r.get("school_id"), str(self.school.pk))
        self.assertNotIn("error", r)
