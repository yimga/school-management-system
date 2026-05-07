from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*", "manager.runmycampus.com"], ROOT_URLCONF="config.urls")
class BlueprintMarketplaceFoundationsTests(TestCase):
    def test_blueprint_facade_lists_required_blueprints_preview_first(self):
        client = Client(HTTP_HOST="manager.runmycampus.com", raise_request_exception=False)
        User.objects.create_user(
            username="blueprint_operator",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        client.login(username="blueprint_operator", password="x" * 8)

        response = client.get("/configuration/blueprints/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        for label in (
            "Private Primary School",
            "Private Secondary School",
            "Cameroon GCE School",
            "Bilingual School",
            "Boarding School",
            "International School",
            "Multi-campus Network",
            "Low-connectivity School",
        ):
            self.assertIn(label, body)
        self.assertIn("installable", body)
        self.assertIn("Impact analysis", body)
        self.assertIn("Installation history", body)
        self.assertIn("/configuration/blueprints/private-primary-school/preview/", body)
        self.assertIn("/configuration/blueprints/installations/", body)
