"""Demo tenant persona seeding."""

from __future__ import annotations

import io

from django.contrib.auth import get_user_model
from django.core.management.color import no_style
from django.test import TestCase

from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.demo_user_seeding import seed_demo_users_for_school
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class SeedDemoUsersForSchoolTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Demo Seed School",
            slug="demo-seed-school",
            is_active=True,
        )
        self.stdout = io.StringIO()
        self.style = no_style()

    def test_creates_student_user_linked_to_profile(self):
        seed_demo_users_for_school(
            self.school,
            password="Test1234",
            username_prefix="demo",
            stdout=self.stdout,
            style=self.style,
        )

        student_user = User.objects.get(username="demo.student")
        self.assertEqual(student_user.role, User.Role.STUDENT)
        self.assertTrue(student_user.check_password("Test1234"))

        profile = StudentProfile.objects.get(student_code__startswith="DEMO-")
        self.assertEqual(profile.user_id, student_user.id)
        self.assertEqual(profile.school_id, self.school.id)

        parent = User.objects.get(username="demo.parent")
        self.assertTrue(
            StudentGuardian.objects.filter(
                guardian_user=parent, student=profile
            ).exists()
        )

        self.assertTrue(
            SchoolMembership.objects.filter(
                user=student_user, school=self.school, role=User.Role.STUDENT
            ).exists()
        )

    def test_idempotent_reseed_keeps_student_link(self):
        seed_demo_users_for_school(
            self.school,
            password="Test1234",
            username_prefix="demo",
            stdout=self.stdout,
            style=self.style,
        )
        profile = StudentProfile.objects.get(student_code__startswith="DEMO-")
        profile_id = profile.id

        seed_demo_users_for_school(
            self.school,
            password="NewPass5678",
            username_prefix="demo",
            stdout=self.stdout,
            style=self.style,
        )

        profile.refresh_from_db()
        self.assertEqual(profile.id, profile_id)
        student_user = User.objects.get(username="demo.student")
        self.assertEqual(profile.user_id, student_user.id)
        self.assertTrue(student_user.check_password("NewPass5678"))
