"""Customer success alert sweep."""

from django.test import TestCase

from apps.customersuccess.tasks import sweep_tenant_health_scores
from apps.schools.models import School


class CustomerSuccessAlertsTests(TestCase):
    def test_health_sweep_writes_scores(self):
        School.objects.create(
            name="Alert School",
            slug="alert-school",
            subdomain="alert-school",
            is_active=True,
        )
        result = sweep_tenant_health_scores(limit=5)
        self.assertGreaterEqual(result["updated"], 1)
