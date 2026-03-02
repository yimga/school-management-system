import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class PublicAccessPointsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runyourcampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "runmycampus.com",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_onboard_route_is_public(self):
        response = self.client.get("/onboard/", HTTP_HOST="runyourcampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Onboard Your Campus")

    def test_regional_routes_exist(self):
        cm = self.client.get("/cm/", HTTP_HOST="runyourcampus.com")
        ca = self.client.get("/ca/", HTTP_HOST="runyourcampus.com")
        fr_cm = self.client.get("/fr/cm/", HTTP_HOST="runyourcampus.com")
        self.assertEqual(cm.status_code, 200)
        self.assertEqual(ca.status_code, 200)
        self.assertEqual(fr_cm.status_code, 200)

    def test_verify_subdomain_isolated(self):
        root = self.client.get("/", HTTP_HOST="verify.runyourcampus.com")
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root["Location"], "/verify/")

        verify = self.client.get("/verify/", HTTP_HOST="verify.runyourcampus.com")
        self.assertEqual(verify.status_code, 200)
        self.assertContains(verify, "Digital ID Verification")

    def test_support_subdomain_isolated(self):
        root = self.client.get("/", HTTP_HOST="support.runyourcampus.com")
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root["Location"], "/support/")

        support = self.client.get("/support/", HTTP_HOST="support.runyourcampus.com")
        self.assertEqual(support.status_code, 200)
        self.assertContains(support, "Global Support Hub")

    def test_public_paths_on_tenant_host_redirect_to_base(self):
        response = self.client.get("/find/?q=gilead", HTTP_HOST="tenant-a.runyourcampus.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://runyourcampus.com/find/?q=gilead")

    def test_unknown_tenant_redirects_to_branded_root_404(self):
        response = self.client.get("/", HTTP_HOST="missing.runyourcampus.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://runyourcampus.com/school-not-found/?slug=missing")

    def test_manager_host_routes_to_dedicated_login_surface(self):
        response = self.client.get("/", HTTP_HOST="manager.runyourcampus.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/authentication/login/")

    def test_marketing_robots_and_sitemap_exist(self):
        robots = self.client.get("/robots.txt", HTTP_HOST="runyourcampus.com")
        sitemap = self.client.get("/sitemap.xml", HTTP_HOST="runyourcampus.com")
        self.assertEqual(robots.status_code, 200)
        self.assertEqual(sitemap.status_code, 200)
        self.assertContains(robots, "Sitemap:")
        self.assertContains(sitemap, "<urlset")

    def test_discover_route_is_public(self):
        response = self.client.get("/discover/", HTTP_HOST="runyourcampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find your school")
