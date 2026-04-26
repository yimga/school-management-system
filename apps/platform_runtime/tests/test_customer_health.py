from django.test import TestCase

from apps.schools.models import School
from apps.platform_runtime.customer_health import (
    calculate_school_health,
    get_school_health_recommendations,
)


class CustomerHealthTests(TestCase):
    def test_no_school_is_setup(self):
        h = calculate_school_health(None)
        self.assertEqual(h["status"], "setup_needed")
        self.assertEqual(h["score"], 0)
        self.assertEqual(get_school_health_recommendations(None), [])

    def test_empty_tenant_tends_setup_needed(self):
        s = School.objects.create(
            name="CH Empty", slug="ch-empty", subdomain="ch-e", is_active=True
        )
        h = calculate_school_health(s)
        self.assertIn(h["status"], ("setup_needed", "at_risk"))
        self.assertLessEqual(h["score"], 50)

    def test_recommendations_respect_limit(self):
        s = School.objects.create(
            name="CH R", slug="ch-r", subdomain="ch-r", is_active=True
        )
        recs = get_school_health_recommendations(s, limit=2)
        self.assertLessEqual(len(recs), 2)
