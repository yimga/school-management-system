from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import School


@override_settings(
    ALLOWED_HOSTS=["*", "tenant-settings.runmycampus.com"],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class TenantSchoolConfigurationCenterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Tenant Settings School",
            slug="tenant-settings",
            subdomain="tenant-settings",
            is_active=True,
        )
        cls.admin = User.objects.create_user(
            username="tenant_settings_admin",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )

    def test_school_configuration_center_returns_200_for_school_admin(self):
        client = Client(HTTP_HOST="tenant-settings.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_settings_admin", password="x" * 8)

        response = client.get("/school/settings/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("School Configuration Center", body)
        self.assertIn("School Profile", body)
        self.assertIn("Academic Year / Term", body)
        self.assertIn("Security / Audit", body)
        self.assertIn("tenant-scoped settings only", body)
        self.assertNotIn("global registries", body.lower())
        self.assertNotIn("system_closure_map", body)

    def test_school_configuration_alias_returns_200(self):
        client = Client(HTTP_HOST="tenant-settings.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_settings_admin", password="x" * 8)

        response = client.get("/siteconfig/school-configuration/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])

    def test_school_product_route_aliases_use_tenant_safe_surfaces(self):
        client = Client(HTTP_HOST="tenant-settings.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_settings_admin", password="x" * 8)

        expected = {
            "/school/apps/": "/settings/app-catalog/",
            "/school/billing/": "/finance/",
            "/school/money/": "/finance/",
            "/school/workflows/": "/studio/automation/",
            "/school/offline/": "/portal/offline-sync/",
            "/school/audit/": "/compliance/",
            "/school/security/": "/compliance/",
        }

        for path, target in expected.items():
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], target)
