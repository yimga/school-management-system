"""Corporate OS public surfaces: status page, find campus, discovery."""

from django.test import Client, TestCase
from django.urls import reverse


class CorporateOsPublicSurfaceTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")

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
