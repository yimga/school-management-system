"""Operator security surface dashboard (read-only generated JSON)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class SuperSecuritySurfaceDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sec_surface_tester",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.host = "manager.runmycampus.com"

    def test_security_surface_dashboard_renders_200(self):
        url = reverse("super:security_surface_dashboard")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Security surface", html=False)
