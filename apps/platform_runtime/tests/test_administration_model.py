from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import School


_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", _MGR_HOST],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class AdministrationModelTests(TestCase):
    def test_internal_admin_alias_preserves_admin_compatibility(self):
        client = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False)

        admin_response = client.get("/admin/")
        alias_response = client.get("/internal-admin/")

        self.assertNotEqual(admin_response.status_code, 404)
        self.assertEqual(alias_response.status_code, 302)
        self.assertEqual(alias_response["Location"], "/admin/")

    def test_tenant_user_is_blocked_from_platform_configuration(self):
        School.objects.create(
            name="Tenant One",
            slug="tenant-one",
            subdomain="tenant-one",
            is_active=True,
        )
        tenant = Client(HTTP_HOST="tenant-one.runmycampus.com", raise_request_exception=False)
        User.objects.create_user(
            username="tenant_cfg_blocked",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        tenant.login(username="tenant_cfg_blocked", password="x" * 8)

        response = tenant.get("/configuration/")

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"control-plane access", response.content)
