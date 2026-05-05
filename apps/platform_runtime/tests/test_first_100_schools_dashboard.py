from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com"],
    ROOT_URLCONF="config.urls",
)
class First100SchoolsDashboardContractTests(TestCase):
    def test_first_100_schools_dashboard_keeps_stage_next_action_and_blocker_context(self):
        User.objects.create_user(
            username="first100_contract_super",
            password="x" * 8,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        self.assertTrue(client.login(username="first100_contract_super", password="x" * 8))

        response = client.get(
            reverse(
                "sales:first_100_schools_dashboard",
                urlconf="config.manager_urls",
            )
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("First 100", body)
        self.assertIn("Pilot", body)
        self.assertIn("Next action", body)
        self.assertIn("Blocker", body)
