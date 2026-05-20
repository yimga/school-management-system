from django.core.cache import cache
from django.test import TestCase, tag

from apps.platform_runtime.entitlement_gates import (
    can_capability,
    gate_summary,
    invalidate_entitlement_cache,
)
from apps.schools.models import School
from apps.siteconfig.models import Plan


@tag("tenants_rls")
class EntitlementPolicyRuntimeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.plan = Plan.objects.create(
            name="Gate Plan",
            slug="gate-plan",
            included_features=["reports"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Gate School",
            slug="gate-school",
            subdomain="gate-school",
            is_active=True,
            plan=self.plan,
        )

    def test_can_capability_respects_plan_features(self):
        self.assertTrue(can_capability(self.school, "reports", use_cache=False))
        self.assertFalse(can_capability(self.school, "migration_cloud", use_cache=False))

    def test_cache_invalidation_changes_subsequent_lookup(self):
        self.assertTrue(can_capability(self.school, "reports", use_cache=True))
        invalidate_entitlement_cache(self.school)
        summary = gate_summary(self.school)
        self.assertEqual(summary["school_id"], self.school.pk)
        self.assertIn("cache_prefix", summary)

    def test_null_school_denied(self):
        self.assertFalse(can_capability(None, "reports"))
