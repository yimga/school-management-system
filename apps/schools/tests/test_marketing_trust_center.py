"""Trust center marketing surface — honest posture, no fake certifications."""

from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class MarketingTrustCenterTests(TestCase):
    def test_route_resolves(self):
        try:
            path = reverse("marketing_trust_dedicated")
        except NoReverseMatch as e:
            self.fail(f"reverse failed: {e}")
        self.assertTrue(path.startswith("/"))

    def test_returns_200_on_canonical_host(self):
        path = reverse("marketing_trust_dedicated")
        client = Client()
        r = client.get(path, HTTP_HOST="runmycampus.com")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace").lower()
        self.assertNotIn("soc 2 certified", body)
        self.assertNotIn("iso 9001 certified", body)
        self.assertIn("psp", body)
        self.assertIn("external", body)
        self.assertIn("contact", body)
