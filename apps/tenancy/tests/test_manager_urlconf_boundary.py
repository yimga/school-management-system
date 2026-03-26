from django.test import TestCase
from django.urls import resolve

from apps.accounts.models import User


class ManagerUrlconfBoundaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="manager_boundary",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.tenant_staff = User.objects.create_user(
            username="tenant_staff_boundary",
            password="testpass123",
            is_staff=True,
            is_superuser=False,
            role=User.Role.ADMIN,
        )

    def test_manager_urlconf_uses_legacy_redirects_for_tenant_prefixes(self):
        match = resolve("/portal/", urlconf="config.manager_urls")
        self.assertEqual(match.url_name, "manager_legacy_portal")

        match = resolve("/finance/", urlconf="config.manager_urls")
        self.assertEqual(match.url_name, "manager_legacy_finance")

    def test_manager_host_rejects_tenant_surface_prefixes(self):
        self.client.force_login(self.user)
        response = self.client.get(
            "/portal/teacher/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

        response = self.client.get("/finance/", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

    def test_manager_search_api_returns_control_plane_results(self):
        self.client.force_login(self.user)
        response = self.client.get(
            "/api/search/?q=billing", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)
        self.assertTrue(
            any(item.get("title") == "Platform Billing" for item in payload["results"]),
            payload,
        )

    def test_manager_search_empty_q_includes_operator_intents(self):
        """Ctrl+K focus: static catalog includes geography, trust, policy, backlog, fleet (BR-02)."""
        self.client.force_login(self.user)
        response = self.client.get(
            "/api/search/?q=", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        titles = [item.get("title") for item in response.json().get("results", [])]
        for needle in (
            "Geography (region packs)",
            "Trust center",
            "Operator policy",
            "Backlog unlock center",
            "Fleet governed changes",
            "Platform operator hub",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, titles)

    def test_manager_search_api_denies_tenant_staff(self):
        self.client.force_login(self.tenant_staff)
        response = self.client.get(
            "/api/search/?q=billing", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 403)
