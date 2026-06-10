"""Tenant health score — customersuccess contract."""

from django.test import TestCase
from django.utils import timezone

from apps.customersuccess.services import compute_tenant_health_score
from apps.schools.models import School


class TenantHealthScoreTests(TestCase):
    def test_score_bounded(self):
        school = School.objects.create(
            name="Score School",
            slug="score-school",
            subdomain="score-school",
            is_active=True,
            created_at=timezone.now(),
        )
        score, dimensions = compute_tenant_health_score(school)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertTrue(dimensions)
