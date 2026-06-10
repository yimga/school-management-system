"""Tenant onboarding nudges."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.customersuccess.tasks import deliver_onboarding_day_n_nudges
from apps.schools.models import School


class TenantOnboardingNudgesTests(TestCase):
    def test_nudge_scan_idempotent(self):
        School.objects.create(
            name="Nudge2",
            slug="nudge2-school",
            subdomain="nudge2-school",
            is_active=True,
            created_at=timezone.now() - timedelta(days=2),
        )
        first = deliver_onboarding_day_n_nudges(limit=10)
        second = deliver_onboarding_day_n_nudges(limit=10)
        self.assertGreaterEqual(first["scanned"], 1)
        self.assertGreaterEqual(second["scanned"], 1)
