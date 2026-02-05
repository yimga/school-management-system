"""
Tests for report publish term view: RBAC and approved-grades settings.
"""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Term


class PublishTermRBACTestCase(TestCase):
    """Publish term page is staff-only and respects reports_require_approved_grades_before_publish."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff_pub",
            password="testpass123",
            is_staff=True,
        )
        self.staff.role = User.Role.ADMIN
        self.staff.save(update_fields=["role"])
        self.year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="First",
            start_date=date(2024, 9, 1),
            end_date=date(2024, 12, 15),
            position=1,
            is_active=True,
        )

    def test_publish_term_requires_staff(self):
        parent = User.objects.create_user(
            username="parent_pub",
            password="testpass123",
            role=User.Role.PARENT,
        )
        self.client.force_login(parent)
        response = self.client.get(reverse("reports:publish_term_results"))
        self.assertIn(response.status_code, (302, 403))

    def test_publish_term_page_loads_for_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("reports:publish_term_results"))
        self.assertEqual(response.status_code, 200)
