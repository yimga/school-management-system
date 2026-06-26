"""Customer success health and nudge tests."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.customersuccess.tasks import deliver_onboarding_day_n_nudges
from apps.schools.models import School


class CustomerSuccessCompletionTests(TestCase):
    def test_onboarding_nudge_task_idempotent(self):
        school = School.objects.create(
            name="Nudge School",
            slug="nudge-school",
            subdomain="nudge-school",
            is_active=True,
            created_at=timezone.now() - timedelta(days=3),
        )
        self.assertIsNotNone(school.pk)
        first = deliver_onboarding_day_n_nudges(limit=5)
        second = deliver_onboarding_day_n_nudges(limit=5)
        self.assertGreaterEqual(first["scanned"], 1)
        self.assertGreaterEqual(second["scanned"], 1)

    def test_health_score_record_exists(self):
        from apps.customersuccess.services import compute_tenant_health_score

        school = School.objects.create(
            name="Health School",
            slug="health-school",
            subdomain="health-school",
            is_active=True,
        )
        score, dimensions = compute_tenant_health_score(school)
        self.assertGreaterEqual(score, 0)
        self.assertIn("activity", dimensions)

    def test_sweep_tenant_health_scores(self):
        from apps.customersuccess.tasks import sweep_tenant_health_scores

        School.objects.create(
            name="Sweep School",
            slug="sweep-school",
            subdomain="sweep-school",
            is_active=True,
        )
        result = sweep_tenant_health_scores(limit=5)
        self.assertGreaterEqual(result["updated"], 1)

    def test_compute_maturity_scores(self):
        from apps.customersuccess.tasks import compute_maturity_scores

        School.objects.create(
            name="Maturity School",
            slug="maturity-school",
            subdomain="maturity-school",
            is_active=True,
        )
        result = compute_maturity_scores(limit=5)
        self.assertGreaterEqual(result["written"], 1)
