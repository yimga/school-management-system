from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client


_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", _MGR_HOST],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class ConfigurationCenterTests(TestCase):
    def setUp(self):
        operator = User.objects.create_user(
            username="platform_config_operator",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        # Manager-host operator page: confirmed device + verified MFA on a
        # manager-bound session (a bare client.login bounces 302 to MFA setup).
        self.client = login_manager_client(operator, password="x" * 8, host=_MGR_HOST)

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
        # The runtime module links its existing system via the CTA "Open runtime
        # truth" → /super/runtime-truth-hub/ (relabelled from "Runtime truth hub").
        self.assertIn("Open runtime truth", body)
        self.assertIn("/super/runtime-truth-hub/", body)
        self.assertNotIn('href="#"', body)
