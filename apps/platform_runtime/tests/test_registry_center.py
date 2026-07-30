from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*", "manager.runmycampus.com"], ROOT_URLCONF="config.urls")
class RegistryCenterTests(TestCase):
    def test_registry_center_lists_existing_registries_and_external_register(self):
        operator = User.objects.create_user(
            username="registry_operator",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        # Manager-host operator page: confirmed device + verified MFA on a
        # manager-bound session (a bare client.login bounces 302 to MFA setup).
        client = login_manager_client(operator, password="x" * 8)

        response = client.get("/configuration/registries/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        for registry in (
            "dashboard_registry",
            "workflow_registry",
            "integration_registry",
            "billing_sku_registry",
            "brand_registry",
            "extension_registry",
            "pack_registry",
            "usage_registry",
            "owned_models_registry",
            "external_dependency_register",
        ):
            self.assertIn(registry, body)
        self.assertIn("external_required", body)
        self.assertNotIn('href="#"', body)
