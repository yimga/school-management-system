"""Corporate OS public surfaces: status page, find campus, discovery."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse


# The Corporate-OS PUBLIC surfaces (status / find-campus / discovery / compliance)
# live on the marketing/public host, whose urlconf is config.public_urls. There,
# /status/ is served by the corporate-OS observability view (data-rmc-os-status-page
# marker + ?format=json JSON probe). On the default config.urls fallback a separate
# siteconfig incident-status page is registered at /status/ FIRST and shadows it.
# UrlConfSwitcherMiddleware routes by HOST — "localhost" is kind="local" → config.urls,
# so the base/marketing host is required to reach public_urls. Pin ROOT_URLCONF too so
# reverse() (called before any request) resolves against the same tree.
@override_settings(
    ROOT_URLCONF="config.public_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ALLOWED_HOSTS=["*"],
)
class CorporateOsPublicSurfaceTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="runmycampus.com")

    def test_status_html_renders(self):
        response = self.client.get(reverse("status"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RunMyCampus platform status")
        self.assertContains(response, "data-rmc-os-status-page")

    def test_status_json_probe(self):
        response = self.client.get(reverse("status"), {"format": "json"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("overall_status", payload)
        self.assertIn("components", payload)

    def test_find_campus_renders_marketing_shell(self):
        response = self.client.get(reverse("find_school"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find your campus portal")
        self.assertContains(response, "data-rmc-os-find-campus")

    def test_global_discovery_renders_marketing_shell(self):
        response = self.client.get(reverse("global_login_discovery"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rmc-os-discovery")

    def test_security_compliance_footer_anchors_present(self):
        response = self.client.get(reverse("marketing_security_compliance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="ferpa"')
        self.assertContains(response, 'id="coppa"')
        self.assertContains(response, 'id="accessibility"')
