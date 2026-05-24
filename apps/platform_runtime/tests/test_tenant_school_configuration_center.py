from __future__ import annotations

from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
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
        TOTPDevice.objects.create(user=cls.admin, name="test-device", confirmed=True)

    def _admin_client(self):
        client = Client(
            HTTP_HOST="tenant-settings.runmycampus.com",
            raise_request_exception=False,
        )
        client.login(username="tenant_settings_admin", password="x" * 8)
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    @staticmethod
    def _store_rendered_templates_without_context_copy(
        store, signal, sender, template, context, **kwargs
    ):
        store.setdefault("templates", []).append(template)
        store.setdefault("context", []).append(context)

    def test_school_configuration_center_returns_200_for_school_admin(self):
        client = self._admin_client()

        response = client.get("/school/settings/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("School Configuration Center", body)
        self.assertIn("School Profile", body)
        self.assertIn("Academic Year / Term", body)
        self.assertIn("Security / Audit", body)
        self.assertIn("tenant scoped only", body.lower())
        self.assertNotIn("global registries", body.lower())
        self.assertNotIn("system_closure_map", body)

    def test_school_configuration_alias_returns_200(self):
        client = self._admin_client()

        response = client.get("/siteconfig/school-configuration/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])

    def test_school_product_route_aliases_use_tenant_safe_surfaces(self):
        client = self._admin_client()

        expected = {
            "/school/apps/": "/settings/app-catalog/",
            "/school/billing/": "/finance/",
            "/school/money/": "/finance/",
            "/school/workflows/": "/studio/automation/",
            "/school/offline/": "/portal/offline/sync-queue/",
            "/school/audit/": "/compliance/dashboard/",
            "/school/security/": "/compliance/dashboard/",
        }

        for path, target in expected.items():
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], target)

        response = client.get("/school/setup/imports/")
        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("School Import Setup", body)
        self.assertIn('data-rmc-workflow-contract="imports"', body)

    def test_school_browser_qa_aliases_resolve_for_tenant_admin(self):
        ComplianceProfile.objects.create(
            name="QA Finance Profile",
            country_code="US",
            currency_code="USD",
            currency_symbol="$",
            is_active=True,
        )
        client = self._admin_client()

        with patch.dict(
            Client.request.__globals__,
            {
                "store_rendered_templates": (
                    self._store_rendered_templates_without_context_copy
                )
            },
        ):
            for path in (
                "/school/setup/imports/",
                "/school/offline/",
                "/school/audit/",
                "/school/security/",
            ):
                with self.subTest(path=path):
                    response = client.get(path, follow=True)
                    self.assertEqual(response.status_code, 200, msg=response.content[:500])
            response = client.get("/school/money/")
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "/finance/")
