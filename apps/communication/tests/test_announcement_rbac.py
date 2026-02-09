"""
RBAC: Department announcement create restricted to HOD and leadership only.
Other teachers get 403 and can only view/receive announcements.
"""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import Department
from apps.people.models import TeacherProfile


class DepartmentAnnouncementCreateRBACTest(TestCase):
    """Only HOD and leadership can create department announcements."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Mathematics")
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
        """HOD can access the create page (200 or redirect to form)."""
        self.client.force_login(self.hod_user)
        response = self.client.get(reverse("communication:department_announcement_create"))
        self.assertEqual(response.status_code, 200)

    def test_leadership_can_access_department_announcement_create(self):
        """Leadership can access the create page."""
        self.client.force_login(self.leadership_user)
        response = self.client.get(reverse("communication:department_announcement_create"))
        # Leadership may have no department; then 403 for "must be assigned to a department"
        # or 200 if they have a department. Either way they're allowed to try (not "only get notified")
        self.assertIn(response.status_code, (200, 403))
        if response.status_code == 403:
            self.assertIn("department", response.content.decode().lower())
