"""Tenant runtime configuration hub — effective settings read surface + permissions."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf

from apps.accounts.models import Permission
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.views_tenant_runtime_hub import tenant_runtime_configuration_hub

User = get_user_model()


class TenantRuntimeConfigurationHubTests(TestCase):
    def test_settings_manage_user_gets_200_and_core_copy(self):
        plan = Plan.objects.create(
            name="Prt",
            slug="prt-rt",
            included_features=["core"],
            is_active=True,
        )
        region = RegionConfig.objects.create(
            code="ZZ",
            name="Testland",
            timezone="UTC",
            default_currency="USD",
        )
        school = School.objects.create(
            name="Runtime High",
            slug="rt-high",
            subdomain="rt-high",
            is_active=True,
            plan=plan,
            default_region=region,
        )
        user = User.objects.create_user(
            username="rtop",
            email="rt@example.com",
            password="x",
            is_staff=False,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        user.feature_permissions.add(manage_perm)

        request = RequestFactory().get("/siteconfig/configuration/runtime/")
        request.user = user
        request.school = school
        set_urlconf("config.tenant_urls")
        try:
            response = tenant_runtime_configuration_hub(request)
        finally:
            set_urlconf(None)
        self.assertEqual(response.status_code, 200)
        content = response.content
        self.assertIn(b"Tenant runtime configuration", content)
        self.assertIn(b"Runtime High", content)
        self.assertIn(b"Testland", content)
        self.assertIn(b"/siteconfig/console/", content)
        self.assertIn(b"/siteconfig/feature-control/", content)

    def test_anonymous_redirects_or_302(self):
        request = RequestFactory().get("/siteconfig/configuration/runtime/")
        request.user = AnonymousUser()
        request.school = None
        set_urlconf("config.tenant_urls")
        try:
            response = tenant_runtime_configuration_hub(request)
        finally:
            set_urlconf(None)
        self.assertIn(response.status_code, (302, 403))
