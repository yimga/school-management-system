from django.test import TestCase
from django.urls import resolve, reverse

from apps.accounts.models import User


class ManagerUrlconfBoundaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="manager_boundary",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )

    def test_manager_urlconf_uses_legacy_redirects_for_tenant_prefixes(self):
        match = resolve("/portal/", urlconf="config.manager_urls")
        self.assertEqual(match.url_name, "manager_legacy_portal")

        match = resolve("/finance/", urlconf="config.manager_urls")
        self.assertEqual(match.url_name, "manager_legacy_finance")

    def test_manager_host_redirects_tenant_surface_to_control_plane(self):
        self.client.force_login(self.user)
        response = self.client.get("/portal/teacher/", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("super:dashboard"))

        response = self.client.get("/finance/", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("super:billing_dashboard"))

    def test_manager_search_api_returns_control_plane_results(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/search/?q=billing", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)
        self.assertTrue(
            any(item.get("title") == "Platform Billing" for item in payload["results"]),
            payload,
        )
