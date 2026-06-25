"""Demo tenant persona seeding."""

from __future__ import annotations

import io

from django.contrib.auth import get_user_model
from django.core.management.color import no_style
from django.test import TestCase

from apps.academics.models import AcademicYear, Term
from apps.finance.models import ComplianceProfile
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.demo_user_seeding import seed_demo_users_for_school
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.config_service import get_effective_site_settings

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

    def test_seed_enables_student_portal_for_school(self):
        self.school.settings = {
            "runtime_defaults": {"enable_student_portal": False},
            "enable_student_portal": False,
        }
        self.school.save(update_fields=["settings"])

        seed_demo_users_for_school(
            self.school,
            password="Test1234",
            username_prefix="demo",
            stdout=self.stdout,
            style=self.style,
        )

        self.school.refresh_from_db()
        rd = (self.school.settings or {}).get("runtime_defaults") or {}
        self.assertTrue(rd.get("enable_student_portal"))
        self.assertTrue((self.school.settings or {}).get("enable_student_portal"))

        site = get_effective_site_settings(school=self.school)
        self.assertTrue(getattr(site, "enable_student_portal", False))

    def test_seed_creates_active_term_and_finance_profile(self):
        seed_demo_users_for_school(
            self.school,
            password="Test1234",
            username_prefix="demo",
            stdout=self.stdout,
            style=self.style,
        )

        year = AcademicYear.objects.filter(school=self.school, is_active=True).first()
        self.assertIsNotNone(year)
        self.assertTrue(
            Term.objects.filter(
                school=self.school, academic_year=year, is_active=True
            ).exists()
        )
        self.assertTrue(ComplianceProfile.objects.filter(is_active=True).exists())
        self.assertTrue(
            TeacherProfile.objects.filter(
                user__username="demo.teacher", school=self.school
            ).exists()
        )
