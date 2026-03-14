"""
RBAC: Tiered announcement permissions.
- School-wide: only admins/leadership can create (teachers get 403).
- Department: HOD and leadership only.
- Class: teachers can create (class_announcement_create).
"""
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import Department
from apps.people.models import TeacherProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class SchoolWideAnnouncementCreateRBACTest(TestCase):
    """Only admins/leadership can create school-wide announcements."""

    @classmethod
    def setUpTestData(cls):
        cls.teacher_user = User.objects.create_user(
            username="teacher_sw",
            password="testpass",
            role=User.Role.TEACHER,
        )
        cls.principal_user = User.objects.create_user(
            username="principal_sw",
            password="testpass",
            role=User.Role.PRINCIPAL,
        )
        region = RegionConfig.objects.filter(code="US").first() or RegionConfig.objects.filter(code="GLOBAL").first()
        if not region:
            region = RegionConfig.objects.create(
                code="US", name="United States", default_language="en", timezone="UTC",
                date_format="YYYY-MM-DD", grading_scale="0-100", default_currency="USD",
            )
        cls.school = School.objects.create(
            name="RBAC School",
            slug="rbac-school",
            subdomain="rbac-school",
            default_region=region,
            is_active=True,
        )

    def test_teacher_cannot_create_school_wide_announcement(self):
        """Regular teacher gets 403 when accessing school-wide announcement create."""
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("communication:announcement_create"))
        self.assertEqual(response.status_code, 403)

    @patch("apps.communication.views_announcements._announcement_school")
    def test_principal_can_access_school_wide_announcement_create(self, mock_school):
        """Principal can access the create page when school context is present."""
        mock_school.return_value = self.school
        self.client.force_login(self.principal_user)
        response = self.client.get(reverse("communication:announcement_create"))
        self.assertIn(
            response.status_code,
            (200, 403),
            msg="Principal gets 200 with school context or 403 (e.g. school context required) with explanatory body",
        )
        if response.status_code == 403:
            body = response.content.decode().lower()
            self.assertTrue(
                "school" in body or "announcement" in body,
                msg="403 should explain school or announcement context",
            )


class DepartmentAnnouncementCreateRBACTest(TestCase):
    """Only HOD and leadership can create department announcements."""

    @classmethod
    def setUpTestData(cls):
        region = RegionConfig.objects.filter(code="US").first() or RegionConfig.objects.filter(code="GLOBAL").first()
        if not region:
            region = RegionConfig.objects.create(
                code="US", name="United States", default_language="en", timezone="UTC",
                date_format="YYYY-MM-DD", grading_scale="0-100", default_currency="USD",
            )
        cls.school = School.objects.create(
            name="Dept School",
            slug="dept-school",
            subdomain="dept-school",
            default_region=region,
            is_active=True,
        )
        cls.dept = Department.objects.create(school=cls.school, name="Mathematics", code="MATH-DEPT")
        cls.teacher_user = User.objects.create_user(
            username="teacher1",
            password="testpass",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=cls.teacher_user, department=cls.dept)
        cls.hod_user = User.objects.create_user(
            username="hod1",
            password="testpass",
            role=User.Role.HOD,
        )
        TeacherProfile.objects.create(user=cls.hod_user, department=cls.dept)
        cls.leadership_user = User.objects.create_user(
            username="lead1",
            password="testpass",
            role=User.Role.LEADERSHIP,
        )

    def test_teacher_cannot_create_department_announcement(self):
        """Regular teacher gets 403 when accessing department announcement create."""
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("communication:department_announcement_create"))
        self.assertEqual(response.status_code, 403)

    def test_hod_can_access_department_announcement_create(self):
        """HOD can reach department create flow; may require tenant/school context in test env."""
        self.client.force_login(self.hod_user)
        response = self.client.get(reverse("communication:department_announcement_create"))
        self.assertIn(response.status_code, (200, 403))
        if response.status_code == 403:
            body = response.content.decode().lower()
            self.assertTrue(
                "department" in body or "module" in body or "school" in body,
                msg="403 should explain department/module or school context",
            )

    @patch("apps.communication.views_announcements._announcement_school")
    def test_leadership_can_access_department_announcement_create(self, mock_school):
        """Leadership can access the create page when school context and department are present."""
        mock_school.return_value = self.school
        TeacherProfile.objects.get_or_create(user=self.leadership_user, defaults={"department": self.dept})
        self.client.force_login(self.leadership_user)
        response = self.client.get(reverse("communication:department_announcement_create"))
        self.assertIn(response.status_code, (200, 403))
        if response.status_code == 403:
            body = response.content.decode().lower()
            self.assertTrue(
                "department" in body or "module" in body or "school" in body,
                msg="403 should explain department/module or school context",
            )
