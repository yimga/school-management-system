"""
Stage 3: admin / configuration / super surfaces — platform-only vs tenant boundaries.
"""

from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, resolve, reverse

from apps.accounts.models import User
from apps.academics.models_tenant_runtime import ReportCardStyleAssignment
from apps.global_registries.models import HolidayCalendar
from apps.schools.models import School
from apps.siteconfig import models as _siteconfig_models
from config.admin import platform_admin_site, tenant_admin_site
from config.schema import schema

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")


class AdminRegistryBoundaryTests(SimpleTestCase):
    def test_platform_and_tenant_registries_are_separate(self):
        self.assertIsNot(platform_admin_site._registry, tenant_admin_site._registry)

    def test_school_model_platform_only(self):
        self.assertIn(School, platform_admin_site._registry)
        self.assertNotIn(School, tenant_admin_site._registry)

    def test_tenant_runtime_models_not_in_platform_admin(self):
        self.assertIn(ReportCardStyleAssignment, tenant_admin_site._registry)
        self.assertNotIn(ReportCardStyleAssignment, platform_admin_site._registry)
        self.assertIn(HolidayCalendar, tenant_admin_site._registry)
        self.assertNotIn(HolidayCalendar, platform_admin_site._registry)

    def test_site_settings_on_tenant_admin_only(self):
        self.assertIn(_TenantSettingsModel, tenant_admin_site._registry)
        self.assertNotIn(_TenantSettingsModel, platform_admin_site._registry)


class AdminPlaneUrlConfTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_admin_uses_platform_admin_site(self):
        match = resolve("/admin/", urlconf="config.manager_urls")
        self.assertIs(match.func.admin_site, platform_admin_site)

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_tenant_admin_uses_tenant_admin_site(self):
        match = resolve("/admin/", urlconf="config.tenant_urls")
        self.assertIs(match.func.admin_site, tenant_admin_site)

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_configuration_namespace_on_manager_only(self):
        reverse("configuration:center", urlconf="config.manager_urls")

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_super_namespace_not_on_tenant_urlconf(self):
        with self.assertRaises(NoReverseMatch):
            reverse("super:dashboard", urlconf="config.tenant_urls")


class ControlPlaneGraphqlBoundaryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superadmin = User.objects.create_user(
            username="edge_superadmin",
            password="testpass123",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=False,
        )
        self.tenant_admin = User.objects.create_user(
            username="edge_tenant_admin",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=False,
        )

    def test_fleet_school_registry_manager_only(self):
        query = "query { schoolCount schools { slug } }"
        manager_request = self.factory.post(
            "/graphql/", data={"query": query}, content_type="application/json"
        )
        manager_request.user = self.superadmin
        manager_request.public_host_kind = "manager"
        manager_result = schema.execute(query, context_value=manager_request)
        self.assertIn("schoolCount", manager_result.data)

        tenant_request = self.factory.post(
            "/graphql/", data={"query": query}, content_type="application/json"
        )
        tenant_request.user = self.tenant_admin
        tenant_request.public_host_kind = "tenant"
        tenant_result = schema.execute(query, context_value=tenant_request)
        self.assertIsNone(tenant_result.data["schoolCount"])
        self.assertEqual(tenant_result.data["schools"], [])
