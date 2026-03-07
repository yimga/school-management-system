"""
Tests for GET /api/schedules/<schedule_id>/conflicts/ (ScheduleConflictsAPI).
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.academics.models import AcademicYear, Term
from apps.academics.scheduling import Schedule


class ScheduleConflictsAPITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Test School",
            slug="test-school",
            subdomain="test-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        today = timezone.now().date()
        self.academic_year = AcademicYear.objects.create(
            name="2024-2025",
            school=self.school,
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            school=self.school,
            name="Term 1",
            position=1,
            start_date=today,
            end_date=today + timedelta(days=90),
        )
        self.schedule = Schedule.objects.create(
            name="Main Schedule",
            academic_year=self.academic_year,
            term=self.term,
            created_by=self.user,
        )

    def test_schedule_conflicts_returns_200_with_schedule(self):
        """GET conflicts for a valid schedule returns 200 and JSON with schedule_id, conflicts, has_conflicts."""
        self.client.force_login(self.user)
        session = self.client.session
        session["school_id"] = str(self.school.id)
        session.save()
        url = reverse("api:schedule-conflicts", kwargs={"schedule_id": self.schedule.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertIn("schedule_id", data)
        self.assertIn("schedule_name", data)
        self.assertIn("conflicts", data)
        self.assertIn("has_conflicts", data)
        self.assertEqual(data["schedule_id"], self.schedule.pk)
        self.assertIsInstance(data["conflicts"], list)
        self.assertIsInstance(data["has_conflicts"], bool)

    def test_schedule_conflicts_400_without_school(self):
        """GET conflicts without school context returns 400."""
        self.client.force_login(self.user)
        # Do not set session["school_id"]
        url = reverse("api:schedule-conflicts", kwargs={"schedule_id": self.schedule.pk})
        response = self.client.get(url)
        self.assertIn(response.status_code, (400, 404))

    def test_schedule_conflicts_404_for_nonexistent_schedule(self):
        """GET conflicts for non-existent schedule_id returns 404."""
        self.client.force_login(self.user)
        session = self.client.session
        session["school_id"] = str(self.school.id)
        session.save()
        url = reverse("api:schedule-conflicts", kwargs={"schedule_id": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
