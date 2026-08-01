from __future__ import annotations

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.platform_runtime.models import PackInstallation
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client


@override_settings(
    ALLOWED_HOSTS=["*", "tenant-packs.runmycampus.com", "manager.runmycampus.com"],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class TenantPackSetupTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Tenant Packs", slug="tenant-packs", subdomain="tenant-packs", is_active=True)
        self.other = School.objects.create(name="Tenant Packs Other", slug="tenant-packs-other", subdomain="tenant-packs-other", is_active=True)
        self.admin = User.objects.create_user(username="tenant_pack_admin", password="x" * 8, role=User.Role.ADMIN, is_staff=True)

    def _admin_client(self):
        # Tenant ADMIN on a tenant-host page needs a SchoolMembership (else
        # OperatorTenantConfinementMiddleware confines the is_staff user to
        # manager/super/ → 302) + confirmed TOTP device + verified session.
        return login_tenant_admin_client(
            self.admin,
            password="x" * 8,
            host="tenant-packs.runmycampus.com",
            school=self.school,
        )

    def test_school_admin_can_access_tenant_pack_setup(self):
        client = self._admin_client()

        response = client.get("/school/setup/packs/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Pack setup", body)
        self.assertIn("Attendance Recovery", body)
        self.assertIn('data-rmc-full-canvas-catalog="tenant-pack"', body)
        self.assertIn('data-rmc-pack-inspector="1"', body)
        self.assertEqual(body.count('data-world-class-tenant-card="1"'), 12)

    def test_catalog_search_and_type_filter_are_server_side_and_paginated(self):
        client = self._admin_client()

        response = client.get(
            "/school/setup/packs/?q=attendance+recovery&catalog_type=workflow_pack"
        )

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Attendance Recovery", body)
        self.assertIn('value="attendance recovery"', body)
        self.assertLessEqual(body.count('data-world-class-tenant-card="1"'), 12)

    def test_invalid_pack_selection_falls_back_to_tenant_safe_catalog(self):
        client = self._admin_client()

        response = client.get(
            "/school/setup/packs/?pack=operator-only-injection&pack_type=policy_bundle"
        )

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertNotIn('value="operator-only-injection"', body)
        self.assertIn('data-rmc-genuine-pack-action="1"', body)

    def test_tenant_apply_only_affects_own_school(self):
        client = self._admin_client()

        response = client.post("/school/setup/packs/", {"pack": "attendance-recovery", "pack_type": "workflow_pack", "confirm": "yes"})

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertTrue(PackInstallation.objects.filter(school=self.school, pack_key="attendance-recovery").exists())
        self.assertFalse(PackInstallation.objects.filter(school=self.other).exists())
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-native-table="1"', body)
        self.assertIn("attendance-recovery", body)

    def test_external_blockers_remain_honest(self):
        client = self._admin_client()

        response = client.get("/school/setup/packs/?pack=finance-approval&pack_type=policy_bundle&preview=1")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertIn("Finance Approval", response.content.decode("utf-8", errors="replace"))
