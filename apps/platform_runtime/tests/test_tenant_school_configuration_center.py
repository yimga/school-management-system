from __future__ import annotations

from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client


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

    def _admin_client(self):
        # Tenant ADMIN on a tenant-host page needs a SchoolMembership (else
        # OperatorTenantConfinementMiddleware confines the is_staff user to
        # manager/super/ → 302) + confirmed TOTP device + verified session.
        return login_tenant_admin_client(
            self.admin,
            password="x" * 8,
            host="tenant-settings.runmycampus.com",
            school=self.school,
        )

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
        # Tenant-scoping guarantee: the MAX parity wave replaced the explicit
        # "tenant scoped only" purpose line with the masthead eyebrow scoping
        # ("Setup · this school") + the per-section permission gate, so assert the
        # rendered scoping signal + the no-operator-plane-leakage invariant.
        self.assertIn("this school", body.lower())
        self.assertNotIn("global registries", body.lower())
        self.assertNotIn("system_closure_map", body)

    def test_school_configuration_alias_returns_200(self):
        client = self._admin_client()

        response = client.get("/siteconfig/school-configuration/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])

    def test_academics_root_and_legacy_aliases_are_live_on_tenant_host(self):
        client = self._admin_client()

        response = client.get("/academics/")
        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-tenant-ops-build="2026-08-01-v1.0"', body)
        self.assertEqual(body.count("<h1"), 1)

        response = client.get("/portal/offline-sync/?state=failed")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/portal/offline/sync-queue/?state=failed")

        response = client.get("/compliance/?period=30d")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/compliance/dashboard/?period=30d")

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
