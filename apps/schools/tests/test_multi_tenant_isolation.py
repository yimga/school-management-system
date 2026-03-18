"""
Multi-tenant isolation: verify queries are scoped to school_id.
Regression tests (Foundation F3) — no cross-tenant data leakage.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.schools.models import School
from apps.finance.models import AwardSource, Scholarship

User = get_user_model()


class MultiTenantIsolationTests(TestCase):
    """Ensure tenant A cannot see tenant B's data when request.school is set."""

    def setUp(self):
        self.school_a = School.objects.create(
            slug="test-school-a",
            subdomain="test-a",
            name="School A",
        )
        self.school_b = School.objects.create(
            slug="test-school-b",
            subdomain="test-b",
            name="School B",
        )
        self.source_a = AwardSource.objects.create(
            school=self.school_a,
            name="Fund A",
            total_budget=10000,
            remaining_funds=10000,
        )
        self.source_b = AwardSource.objects.create(
            school=self.school_b,
            name="Fund B",
            total_budget=5000,
            remaining_funds=5000,
        )

    def test_award_sources_scoped_by_school(self):
        """AwardSource queryset filtered by school returns only that school's sources."""
        qs_a = AwardSource.objects.filter(school=self.school_a)
        qs_b = AwardSource.objects.filter(school=self.school_b)
        self.assertEqual(qs_a.count(), 1)
        self.assertEqual(qs_b.count(), 1)
        self.assertIn(self.source_a, qs_a)
        self.assertNotIn(self.source_a, qs_b)
        self.assertIn(self.source_b, qs_b)
        self.assertNotIn(self.source_b, qs_a)

    def test_scholarships_scoped_by_school(self):
        """Scholarship creation and list are school-scoped."""
        Scholarship.objects.create(
            school=self.school_a,
            source=self.source_a,
            title="Grant A",
            award_amount=500,
        )
        Scholarship.objects.create(
            school=self.school_b,
            source=self.source_b,
            title="Grant B",
            award_amount=300,
        )
        self.assertEqual(Scholarship.objects.filter(school=self.school_a).count(), 1)
        self.assertEqual(Scholarship.objects.filter(school=self.school_b).count(), 1)
        for s in Scholarship.objects.filter(school=self.school_a):
            self.assertEqual(s.school_id, self.school_a.pk)
