from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, resolve, reverse

from apps.accounts.models import User
from apps.accounts.permissions import can_access_module
from config.admin import platform_admin_site, tenant_admin_site
from config.schema import schema


class ControlPlaneBoundaryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superadmin = User.objects.create_user(
            username="cp_superadmin",
            password="testpass123",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=False,
        )
        self.tenant_admin = User.objects.create_user(
            username="tenant_admin_boundary",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=False,
        )

    def test_superadmin_role_no_longer_grants_tenant_module_access(self):
        self.assertFalse(can_access_module(self.superadmin, "finance", action="read"))
        self.assertFalse(can_access_module(self.superadmin, "portal", action="write"))

    def test_global_school_registry_is_control_plane_only(self):
        query = "query { schoolCount schools { slug } }"

        manager_request = self.factory.post("/graphql/", data={"query": query}, content_type="application/json")
        manager_request.user = self.superadmin
        manager_request.public_host_kind = "manager"
        manager_result = schema.execute(query, context_value=manager_request)
        self.assertIn("schoolCount", manager_result.data)
        self.assertIn("schools", manager_result.data)

        tenant_request = self.factory.post("/graphql/", data={"query": query}, content_type="application/json")
        tenant_request.user = self.tenant_admin
        tenant_request.public_host_kind = "tenant"
        tenant_result = schema.execute(query, context_value=tenant_request)
        self.assertIsNone(tenant_result.data["schoolCount"])
        self.assertEqual(tenant_result.data["schools"], [])


class AdminPlaneUrlConfTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_urlconf_uses_platform_admin_site_without_tenant_namespaces(self):
        match = resolve("/admin/")
        self.assertIs(match.func.admin_site, platform_admin_site)
        with self.assertRaises(NoReverseMatch):
            reverse("portal:parent_dashboard")
        with self.assertRaises(NoReverseMatch):
            reverse("kb:kb_home")

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_tenant_urlconf_uses_tenant_admin_site_with_tenant_namespaces(self):
        match = resolve("/admin/")
        self.assertIs(match.func.admin_site, tenant_admin_site)
        self.assertTrue(reverse("portal:parent_dashboard").startswith("/portal/"))
