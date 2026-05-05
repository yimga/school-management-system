from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class PilotEvidenceBoardContractTests(TestCase):
    def test_pilot_evidence_board_renders_without_fake_public_references(self):
        User.objects.create_user(
            username="pilot_board_super",
            password="x" * 8,
            is_superuser=True,
        )
        client = Client()
        self.assertTrue(client.login(username="pilot_board_super", password="x" * 8))

        response = client.get(
            reverse("platform_runtime:pilot_evidence_dashboard"),
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Pilot evidence", body)
        self.assertIn("testimonial", body.lower())
        self.assertNotIn("public customer logo", body.lower())
