"""Manager host legal/marketing pages must render without public-only URL names."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

_MANAGER_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MANAGER_HOST],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    PUBLIC_SITE_URL="https://runmycampus.com",
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="config.manager_urls",
)
class ManagerMarketingLegalPageTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=_MANAGER_HOST)

    def test_privacy_page_renders_on_manager_host(self):
        response = self.client.get("/privacy/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"privacy", response.content.lower())

    def test_marketing_demo_named_route_redirects_to_public_host(self):
        response = self.client.get("/demo/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("runmycampus.com", response["Location"])
        self.assertIn("/demo", response["Location"])

    def test_marketing_demo_reverses_on_manager_urlconf(self):
        self.assertEqual(reverse("marketing_demo"), "/demo/")

    def test_tour_steps_api_reverses_on_manager_urlconf(self):
        self.assertEqual(
            reverse("tour_steps_public_api"),
            "/api/tour-steps/public/",
        )
