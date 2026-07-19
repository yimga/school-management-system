"""PRODUCTION_READINESS A2: missing teacher/student profile returns 404, not 500."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class DashboardAPIProfile404Tests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_teacher_dashboard_without_profile_returns_404(self):
        u = User.objects.create_user(
            username="t_no_prof",
            email="t@example.com",
            password="x",
        )
        u.role = User.Role.TEACHER
        u.save(update_fields=["role"])
        self.client.force_login(u)
        # Login bootstrap may auto-stub TeacherProfile; API must 404 without a real profile.
        from apps.people.models import TeacherProfile

        TeacherProfile.objects.filter(user=u).delete()
        url = reverse("api:teacher-dashboard")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)
        data = r.json()
        self.assertIn("error", data)
        self.assertIn("not found", data["error"].lower())

    def test_student_dashboard_without_profile_returns_404(self):
        u = User.objects.create_user(
            username="s_no_prof",
            email="s@example.com",
            password="x",
        )
        u.role = User.Role.STUDENT
        u.save(update_fields=["role"])
        self.client.force_login(u)
        url = reverse("api:student-dashboard")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)
        data = r.json()
        self.assertIn("not found", data["error"].lower())
