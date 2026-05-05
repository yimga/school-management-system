from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["*", "testserver"], ROOT_URLCONF="config.urls")
class TrustProcurementSurfaceTests(TestCase):
    def test_trust_procurement_routes_return_200_and_keep_honesty(self):
        routes = [
            "marketing_trust_dedicated",
            "marketing_procurement_checklist",
            "marketing_implementation_assurance",
            "marketing_security_packet_request",
            "marketing_story_payments_readiness",
        ]
        client = Client()

        for route in routes:
            with self.subTest(route=route):
                response = client.get(reverse(route))
                self.assertEqual(response.status_code, 200, msg=response.content[:300])
                body = response.content.decode("utf-8", errors="replace")
                self.assertIn("Book", body)
                self.assertNotIn("SOC 2 certified", body)
                self.assertNotIn("ISO 27001 certified", body)
                self.assertNotIn("PCI certified", body)
                self.assertNotIn("live PSP ready", body.lower())

    def test_procurement_surfaces_expose_security_packet_and_external_caveat(self):
        client = Client()
        response = client.get(reverse("marketing_procurement_checklist"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Request security packet", body)
        self.assertIn("procurement checklist", body.lower())
        self.assertIn("external", body.lower())
