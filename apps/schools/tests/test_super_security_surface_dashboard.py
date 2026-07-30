"""Operator security surface dashboard (read-only generated JSON)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*"])
class SuperSecuritySurfaceDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sec_surface_tester",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        # Manager-host operator page: bind the manager session with confirmed +
        # verified MFA (bare force_login bounces 302 through RequireMFAMiddleware).
        self.client = login_manager_client(self.user, password="testpass123")
        self.host = "manager.runmycampus.com"

    def test_security_surface_dashboard_renders_200(self):
        url = reverse("super:security_surface_dashboard")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Security surface", html=False)
