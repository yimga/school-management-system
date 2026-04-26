from django.test import TestCase
from django.urls import resolve, set_urlconf

from apps.accounts.models import User

from config.manager_urls import _manager_search_static_catalog


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

    def test_manager_urlconf_mounts_automation_outcomes_console(self):
        match = resolve("/automation/outcomes/", urlconf="config.manager_urls")
        self.assertEqual(match.url_name, "outcomes_console")

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
            "Schools list",
            "Analytics overview",
            "Geography (region packs)",
            "Trust center",
            "Operator policy",
            "Backlog unlock center",
            "Fleet governed changes",
            "Platform operator hub",
            "Playbook operator hub",
            "Runtime truth hub",
            "Workflow simulator",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, titles)

    def test_manager_search_empty_q_includes_runtime_surfaces(self):
        """Empty-q Ctrl+K catalog includes playbook / runtime truth / workflow simulator."""
        self.client.force_login(self.user)
        response = self.client.get(
            "/api/search/?q=", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        titles = [item.get("title") for item in response.json().get("results", [])]
        for needle in (
            "Playbook operator hub",
            "Runtime truth hub",
            "Workflow simulator",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, titles)

    def test_manager_search_empty_q_returns_full_static_catalog(self):
        """Empty query must not truncate the curated catalog (incl. Workflow simulator)."""
        self.client.force_login(self.user)
        r = self.client.get("/api/search/?q=", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        got = r.json().get("results", [])
        # `reverse()` for manager-only names needs the control-plane urlconf, same as the view.
        set_urlconf("config.manager_urls")
        try:
            expected = _manager_search_static_catalog()
        finally:
            set_urlconf(None)
        self.assertEqual(
            len(got),
            len(expected),
            msg="manager_search_api empty-q path must return the full static catalog",
        )
        by_title = {x.get("title") for x in got}
        for item in expected:
            self.assertIn(item["title"], by_title)

    def test_manager_search_api_denies_tenant_staff(self):
        self.client.force_login(self.tenant_staff)
        response = self.client.get(
            "/api/search/?q=billing", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 403)
