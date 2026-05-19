"""Repo-contained first-school operating path smoke (no live PSP)."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.onboarding import get_school_onboarding_progress
from apps.schools.models import School, SchoolMembership


class FirstSchoolOperatingProofTests(TestCase):
    def test_school_create_and_onboarding_progress(self):
        school = School.objects.create(name="Proof School", slug="proof-school")
        admin = User.objects.create_user(
            username="proof_admin",
            password="Test1234!",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(user=admin, school=school, role=User.Role.ADMIN)
        progress = get_school_onboarding_progress(school)
        self.assertIsInstance(progress, dict)
        self.assertIn("percent", progress)
        self.assertTrue(admin.pk)
        self.assertTrue(reverse("accounts:backend_dashboard"))
