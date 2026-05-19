"""Theme & experience hub — tenant and manager dual-plane entry points."""

from __future__ import annotations

import uuid

from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission, User
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.schools.models import School, SchoolMembership
from apps.test_utils.http_clients import login_manager_client, login_tenant_client


_TENANT_SETTINGS = dict(
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
)
_MANAGER_SETTINGS = dict(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com"],
    ROOT_URLCONF="config.manager_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
)


class ThemeExperienceHubTests(TransactionTestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex[:8]
        self.tenant_host = f"theme-hub-school-{suffix}.runmycampus.com"
        self.school = School.objects.create(
            name="Theme Hub School",
            slug=f"theme-hub-school-{suffix}",
            subdomain=f"theme-hub-school-{suffix}",
            is_active=True,
        )
        get_platform_site_settings_record(create=True)
        self.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.tenant_admin = User.objects.create_user(
            username=f"theme-hub-admin-{suffix}",
            password="password",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.tenant_admin.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=self.tenant_admin,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        TOTPDevice.objects.update_or_create(
            user=self.tenant_admin,
            name="test-mfa",
            defaults={"confirmed": True},
        )
        self.operator = User.objects.create_superuser(
            username=f"theme-hub-operator-{suffix}",
            password="password",
            email=f"op-{suffix}@example.com",
        )

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_hub_lists_school_surfaces(self):
        client = login_tenant_client(
            self.tenant_admin,
            password="password",
            host=self.tenant_host,
        )
        response = client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("School theme", body)
        self.assertIn("studio", body.lower())
        self.assertIn("data-rmc-theme-hub-hero", body)
        self.assertIn("theme-builder", body.lower())

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_hub_includes_builder_hero_preview(self):
        client = login_tenant_client(
            self.tenant_admin,
            password="password",
            host=self.tenant_host,
        )
        response = client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open theme builder")
        self.assertContains(response, "theme-hub-mini-preview")

    @override_settings(**_MANAGER_SETTINGS)
    def test_manager_hub_lists_platform_surfaces(self):
        client = login_manager_client(self.operator, password="password")
        response = client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Platform theme", body)
        self.assertIn("/configuration/experience/", body)

    @override_settings(**_TENANT_SETTINGS)
    def test_legacy_theme_experience_redirects_to_hub_on_tenant(self):
        client = login_tenant_client(
            self.tenant_admin,
            password="password",
            host=self.tenant_host,
        )
        response = client.get(reverse("siteconfig:theme_experience_redirect"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("siteconfig:theme_experience_hub"), response.url)

    @override_settings(**_MANAGER_SETTINGS)
    def test_manager_hub_shows_impersonation_cta(self):
        client = login_manager_client(self.operator, password="password")
        response = client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open schools registry")

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_hub_forbidden_without_settings_manage(self):
        user = User.objects.create_user(
            username=f"theme-hub-teacher-{uuid.uuid4().hex[:8]}",
            password="password",
            role=User.Role.TEACHER,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role="TEACHER",
            is_primary=True,
        )
        client = login_tenant_client(
            user,
            password="password",
            host=self.tenant_host,
        )
        response = client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertIn(response.status_code, (302, 403))
