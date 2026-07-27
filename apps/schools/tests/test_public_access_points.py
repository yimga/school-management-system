import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class PublicAccessPointsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_onboard_route_is_public(self):
        response = self.client.get("/onboard/", HTTP_HOST="runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Onboard Your Campus")

    def test_regional_routes_exist(self):
        cm = self.client.get("/cm/", HTTP_HOST="runmycampus.com")
        ca = self.client.get("/ca/", HTTP_HOST="runmycampus.com")
        fr_cm = self.client.get("/fr/cm/", HTTP_HOST="runmycampus.com")
        self.assertEqual(cm.status_code, 200)
        self.assertEqual(ca.status_code, 200)
        self.assertEqual(fr_cm.status_code, 200)

    def test_verify_subdomain_isolated(self):
        root = self.client.get("/", HTTP_HOST="verify.runmycampus.com")
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root["Location"], "/verify/")

        verify = self.client.get("/verify/", HTTP_HOST="verify.runmycampus.com")
        self.assertEqual(verify.status_code, 200)
        self.assertContains(verify, "Digital ID Verification")

    def test_support_subdomain_isolated(self):
        root = self.client.get("/", HTTP_HOST="support.runmycampus.com")
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root["Location"], "/support/")

        support = self.client.get("/support/", HTTP_HOST="support.runmycampus.com")
        self.assertEqual(support.status_code, 200)
        self.assertContains(support, "Global Support Hub")

    def test_public_paths_on_tenant_host_redirect_to_base(self):
        response = self.client.get(
            "/find/?q=legacy-campus", HTTP_HOST="tenant-a.runmycampus.com"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"], "https://runmycampus.com/find/?q=legacy-campus"
        )

    def test_unknown_tenant_redirects_to_branded_root_404(self):
        response = self.client.get("/", HTTP_HOST="missing.runmycampus.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://runmycampus.com/school-not-found/?slug=missing",
        )

    def test_manager_host_routes_to_dedicated_login_surface(self):
        response = self.client.get("/", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 302)
        # ?cp=1 selects the dedicated control-plane login surface (operator-branded)
        # — exactly the "dedicated login surface" this test asserts. The manager
        # root appends it so the operator lands on the CP login, not the tenant one.
        self.assertEqual(response["Location"], "/authentication/login/?cp=1")

    def test_manager_host_auth_root_redirects_to_login(self):
        response = self.client.get(
            "/authentication/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

    def test_tenant_host_auth_root_redirects_to_login(self):
        School.objects.create(
            name="Tenant Alpha",
            slug="tenant-alpha",
            subdomain="tenant-alpha",
            is_active=True,
        )
        response = self.client.get(
            "/authentication/", HTTP_HOST="tenant-alpha.runmycampus.com"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/authentication/login/")

    def test_marketing_robots_and_sitemap_exist(self):
        robots = self.client.get("/robots.txt", HTTP_HOST="runmycampus.com")
        sitemap = self.client.get("/sitemap.xml", HTTP_HOST="runmycampus.com")
        self.assertEqual(robots.status_code, 200)
        self.assertEqual(sitemap.status_code, 200)
        self.assertContains(robots, "Sitemap:")
        self.assertContains(sitemap, "<urlset")

    def test_discover_route_is_public(self):
        response = self.client.get("/discover/", HTTP_HOST="runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find your school")

    def test_render_probe_auth_login_on_base_host_returns_200(self):
        # The base/marketing host sends an anonymous /authentication/login/ to the
        # school-discovery page (no tenant context on the base host — you find your
        # campus, then sign in on its subdomain). A Render deploy probe therefore
        # lands on a healthy 200 page after one redirect; follow it and assert the
        # URL is reachable/healthy (not a 404/500 or tenant-misroute).
        response = self.client.get(
            "/authentication/login/",
            HTTP_HOST="school-management-system-2kzk.onrender.com",
            HTTP_USER_AGENT="Render/1.0",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

    def test_health_endpoint_returns_200_on_render_host(self):
        response = self.client.get(
            "/health/",
            HTTP_HOST="school-management-system-2kzk.onrender.com",
            HTTP_USER_AGENT="Render/1.0",
        )
        self.assertEqual(response.status_code, 200)

    def test_marketing_base_url_context_processor_uses_canonical_domain(self):
        """Cross-host links from tenant/manager should use MARKETING_BASE_URL (canonical apex)."""
        from apps.schools.context_processors import marketing_base_url
        from django.test import RequestFactory

        rf = RequestFactory()
        req = rf.get("/", HTTP_HOST="tenant-a.runmycampus.com", secure=True)
        ctx = marketing_base_url(req)
        self.assertIn("MARKETING_BASE_URL", ctx)
        self.assertEqual(ctx["MARKETING_BASE_URL"], "https://runmycampus.com")
