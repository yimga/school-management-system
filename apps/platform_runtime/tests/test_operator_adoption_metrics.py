"""Operator adoption metrics — honest insufficient-data paths."""

from django.test import TestCase

from apps.platform_runtime.models import PlatformEventLog
from apps.platform_runtime.operator_adoption_metrics import compute_operator_adoption_metrics
from apps.schools.models import School


class OperatorAdoptionMetricsTests(TestCase):
    databases = {"default"}

    def test_insufficient_without_school_ids(self):
        m = compute_operator_adoption_metrics([])
        self.assertTrue(m["insufficient_data"])

    def test_insufficient_without_events(self):
        s = School.objects.create(
            name="Adopt School",
            slug="adopt-school",
            subdomain="adopt-school",
            country_code="CM",
            is_active=True,
        )
        m = compute_operator_adoption_metrics([s.pk])
        self.assertTrue(m["insufficient_data"])

    def test_signals_when_events_exist(self):
        s = School.objects.create(
            name="Adopt2",
            slug="adopt-2",
            subdomain="adopt-2",
            country_code="CM",
            is_active=True,
        )
        PlatformEventLog.objects.create(
            event_type="first_action",
            school_id=str(s.pk),
            payload={},
        )
        m = compute_operator_adoption_metrics([s.pk])
        self.assertFalse(m["insufficient_data"])
        self.assertTrue(m["first_action_completed"])
