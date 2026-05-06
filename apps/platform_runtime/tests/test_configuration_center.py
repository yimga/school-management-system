from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User


_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", _MGR_HOST],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class ConfigurationCenterTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False)
        User.objects.create_user(
            username="platform_config_operator",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        self.client.login(username="platform_config_operator", password="x" * 8)

    def test_configuration_center_renders_required_modules(self):
        response = self.client.get("/configuration/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        for label in (
            "Blueprint Marketplace",
            "App Catalog",
            "Package Rollout",
            "Workflow Packs",
            "Dashboard Packs",
            "Policy Bundles",
            "Metadata Catalog",
            "Registry Center",
            "Runtime + Governance",
            "Migration Center",
            "Integration + API Center",
            "Compliance + Audit Configuration",
            "Security + Trust Configuration",
            "Billing / Subscription / Usage Rules",
            "UX/UI Experience Configuration",
        ):
            self.assertIn(label, body)
        self.assertIn('data-rmc-os-center="platform_configuration_center"', body)
        self.assertIn("external_required", body)
        self.assertNotIn('href="#"', body)
        self.assertNotIn('href=""', body)

    def test_configuration_detail_links_existing_system(self):
        response = self.client.get("/configuration/runtime/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Runtime + Governance", body)
        self.assertIn("Runtime truth", body)
        self.assertNotIn('href="#"', body)
