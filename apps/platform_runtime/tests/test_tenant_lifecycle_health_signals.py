"""Tenant lifecycle health signals."""

from django.test import TestCase

from apps.customersuccess.services import compute_tenant_health_score
from apps.schools.models import School


class TenantLifecycleHealthSignalsTests(TestCase):
    def test_dimensions_include_setup_signal(self):
        school = School.objects.create(
            name="Signal School",
            slug="signal-school",
            subdomain="signal-school",
            is_active=True,
        )
        _, dimensions = compute_tenant_health_score(school)
        self.assertTrue(any(k in dimensions for k in ("activity", "workflows", "adoption")))
