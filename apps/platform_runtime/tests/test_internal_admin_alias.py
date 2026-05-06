from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.schools.models import School


@override_settings(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com", "school-admin.runmycampus.com"],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class InternalAdminAliasTests(TestCase):
    def test_manager_internal_admin_alias_redirects_to_platform_admin_mount(self):
        response = Client(HTTP_HOST="manager.runmycampus.com").get(
            "/internal-admin/auth/user/"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/admin/auth/user/")

    def test_tenant_internal_admin_alias_redirects_to_tenant_admin_mount(self):
        School.objects.create(
            name="School Admin",
            slug="school-admin",
            subdomain="school-admin",
            is_active=True,
        )
        response = Client(HTTP_HOST="school-admin.runmycampus.com").get(
            "/internal-admin/auth/user/"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/admin/auth/user/")
